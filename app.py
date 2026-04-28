from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pypdf
import docx
import io
import boto3
import os
import meilisearch
import uuid
import datetime
import regex
import translate
from sqlalchemy import create_engine, Column, String, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/search_docs")
Base = declarative_base()

class DocumentMetadata(Base):
    __tablename__ = 'documents'
    id = Column(String, primary_key=True)
    filename = Column(String)
    storage_key = Column(String)
    meili_id = Column(String)
    missing_fields = Column(JSON)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")

# Meilisearch Configuration
MEILI_HTTP_ADDR = os.getenv("MEILI_HTTP_ADDR", "http://localhost:7700")
MEILI_MASTER_KEY = os.getenv("MEILI_MASTER_KEY", "masterKey")
MEILI_INDEX_NAME = os.getenv("MEILI_INDEX", "documents")

# Initialize Clients
s3_client = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name="us-east-1"
)

meili_client = meilisearch.Client(MEILI_HTTP_ADDR, MEILI_MASTER_KEY)

# Ensure services are ready
def init_services():
    # Database
    try:
        Base.metadata.create_all(bind=engine)
        print("PostgreSQL: Tables verified/created.")
    except Exception as e:
        print(f"PostgreSQL Connection Error: {e}")

    # MinIO
    try:
        s3_client.head_bucket(Bucket=MINIO_BUCKET)
        print(f"MinIO: Bucket '{MINIO_BUCKET}' verified.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            s3_client.create_bucket(Bucket=MINIO_BUCKET)
            print(f"MinIO: Bucket '{MINIO_BUCKET}' created.")
        else:
            print(f"MinIO error: {e}")
    except Exception as e:
        print(f"MinIO Connection Error: {e}")

    # Meilisearch
    try:
        meili_client.create_index(MEILI_INDEX_NAME, {"primaryKey": "id"})
        print(f"Meilisearch: Index '{MEILI_INDEX_NAME}' created.")
    except Exception as e:
        # Index might already exist, which is fine
        if "index_already_exists" in str(e):
            print(f"Meilisearch: Index '{MEILI_INDEX_NAME}' verified.")
        else:
            print(f"Meilisearch Connection Error: {e}")

init_services()

# Dependency for DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    print(f"Response: {response.status_code}")
    return response

def extract_text_from_pdf(file_bytes):
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e)}")

def extract_text_from_docx(file_bytes):
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing DOCX: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Document Search API with PostgreSQL Persistence is running"}

@app.get("/documents")
async def get_documents():
    db = SessionLocal()
    try:
        docs = db.query(DocumentMetadata).order_by(DocumentMetadata.created_at.desc()).all()
        return [{"id": d.id, "filename": d.filename, "created_at": d.created_at, "source": "db"} for d in docs]
    finally:
        db.close()

@app.get("/minio-files")
async def get_minio_files():
    try:
        response = s3_client.list_objects_v2(Bucket=MINIO_BUCKET)
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                files.append({
                    "filename": obj['Key'],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "source": "minio"
                })
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO error: {str(e)}")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    extension = file.filename.split(".")[-1].lower()
    content = await file.read()
    doc_id = str(uuid.uuid4())
    
    # 1. Upload to MinIO
    try:
        s3_client.put_object(
            Bucket=MINIO_BUCKET,
            Key=file.filename,
            Body=content,
            ContentType=file.content_type
        )
    except Exception as e:
        print(f"MinIO Upload Error: {e}")
        # We continue even if storage fails, though ideally it shouldn't

    # 2. Extract text
    if extension == "pdf":
        text = extract_text_from_pdf(content)
    elif extension in ["docx", "doc"]:
        try:
            text = extract_text_from_docx(content)
        except Exception:
            raise HTTPException(status_code=400, detail="Legacy .doc format is not supported.")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    # 2.5 Translate text to English
    try:
        text = translate.translate_to_english(text)
    except Exception as e:
        print(f"Translation Error: {e}")

    # 3. Index in Meilisearch
    try:
        meili_client.index(MEILI_INDEX_NAME).add_documents([{
            "id": doc_id,
            "filename": file.filename,
            "text": text,
            "extension": extension
        }])
    except Exception as e:
        print(f"Meilisearch Indexing Error: {e}")

    # 4. Check for missing fields
    missing_fields = regex.check_missing_fields(text)

    # 5. Save to PostgreSQL
    db = SessionLocal()
    try:
        db_doc = DocumentMetadata(
            id=doc_id,
            filename=file.filename,
            storage_key=file.filename,
            meili_id=doc_id,
            missing_fields=missing_fields
        )
        db.add(db_doc)
        db.commit()
    except Exception as e:
        print(f"PostgreSQL Error: {e}")
    finally:
        db.close()

    return {
        "id": doc_id,
        "filename": file.filename,
        "storage": "MinIO + PostgreSQL",
        "search": "Meilisearch Indexed",
        "missing_fields": missing_fields
    }

@app.get("/search")
async def search(q: str):
    try:
        index = meili_client.index(MEILI_INDEX_NAME)
        results = index.search(q, {
            "attributesToHighlight": ["text"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "attributesToCrop": ["text"],
            "cropLength": 50
        })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meilisearch search error: {str(e)}")

@app.get("/documents/{doc_id}")
async def get_document_details(doc_id: str):
    print(f"Fetching details for doc_id: {doc_id}")
    try:
        db = SessionLocal()
        db_doc = db.query(DocumentMetadata).filter(DocumentMetadata.id == doc_id).first()
        db.close()

        if not db_doc:
            raise HTTPException(status_code=404, detail="Document not found in database")

        text = ""
        try:
            # Try to get text from Meilisearch
            doc = meili_client.index(MEILI_INDEX_NAME).get_document(doc_id)
            text = doc.get("text", "")
        except Exception:
            print(f"Meilisearch missing doc {doc_id}. Re-extracting from MinIO...")
            # Fallback: Extract from MinIO
            try:
                response = s3_client.get_object(Bucket=MINIO_BUCKET, Key=db_doc.storage_key)
                content = response['Body'].read()
                extension = db_doc.filename.split(".")[-1].lower()
                
                if extension == "pdf":
                    text = extract_text_from_pdf(content)
                elif extension in ["docx", "doc"]:
                    text = extract_text_from_docx(content)
                
                # Translate fallback text
                try:
                    text = translate.translate_to_english(text)
                except Exception as t_err:
                    print(f"Fallback Translation Error: {t_err}")

                # Re-index in Meilisearch for next time
                meili_client.index(MEILI_INDEX_NAME).add_documents([{
                    "id": doc_id,
                    "filename": db_doc.filename,
                    "text": text,
                    "extension": extension
                }])
            except Exception as s3_err:
                print(f"MinIO/Extraction error: {s3_err}")
                text = "Error: Could not extract text from storage."

        return {
            "id": db_doc.id,
            "filename": db_doc.filename,
            "text": text,
            "missing_fields": db_doc.missing_fields,
            "created_at": db_doc.created_at
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Server error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{doc_id}/validate")
async def validate_document(doc_id: str):
    print(f"Validating doc_id: {doc_id}")
    try:
        # Get document text using the logic above
        details = await get_document_details(doc_id)
        text = details.get("text", "")
        
        if not text or text.startswith("Error:"):
            raise HTTPException(status_code=404, detail="Document text not available for validation")

        missing_fields = regex.check_missing_fields(text)
        
        # Update DB
        db = SessionLocal()
        db_doc = db.query(DocumentMetadata).filter(DocumentMetadata.id == doc_id).first()
        if db_doc:
            db_doc.missing_fields = missing_fields
            db.commit()
        db.close()
        
        return {"id": doc_id, "missing_fields": missing_fields}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
