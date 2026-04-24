from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pypdf
import docx
import io
import boto3
import os
import meilisearch
import uuid
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
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
            print(f"Meilisearch Connection Error: {e}. Please ensure Meilisearch is running.")

init_services()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {"message": "Document Search API with MinIO & Meilisearch is running"}

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
            raise HTTPException(status_code=400, detail="Legacy .doc format is not supported. Please use .docx")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format.")

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

    return {
        "id": doc_id,
        "filename": file.filename,
        "text": text,
        "storage": "MinIO",
        "search": "Meilisearch Indexed"
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
