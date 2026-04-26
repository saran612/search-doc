const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const resultsContainer = document.getElementById('results');

let documents = [];

// Drag and drop handlers
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();meilisearch
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const files = e.dataTransfer.files;
    handleFiles(files);
});

dropZone.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', () => {
    handleFiles(fileInput.files);
});

async function handleFiles(files) {
    for (const file of files) {
        if (file.type === 'application/pdf' || file.name.endsWith('.docx')) {
            uploadFile(file);
        } else {
            alert('Please upload only PDF or DOCX files.');
        }
    }
}

async function uploadFile(file) {
    const fileId = Date.now();
    addFileToUI(file.name, fileId, 'Uploading...');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('http://localhost:8000/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const data = await response.json();
        updateFileStatus(fileId, '✅', `Stored in ${data.storage}`);
        
    } catch (error) {
        console.error('Error:', error);
        updateFileStatus(fileId, '❌', error.message);
    }
}

function addFileToUI(name, id, statusText) {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.id = `file-${id}`;
    item.innerHTML = `<div class="file-row"><span>${name}</span> <span class="status">${statusText}</span></div>`;
    fileList.appendChild(item);
    return item;
}

function updateFileStatus(id, icon, storageInfo) {
    const item = document.getElementById(`file-${id}`);
    if (!item) return;
    
    item.querySelector('.status').textContent = icon;
    
    if (storageInfo) {
        const info = document.createElement('div');
        info.style.fontSize = '10px';
        info.style.color = '#555';
        info.textContent = storageInfo;
        item.appendChild(info);
    }
}

// Fetch existing documents on load
async function loadDocuments() {
    try {
        const response = await fetch('http://localhost:8000/minio-files');
        if (!response.ok) throw new Error('Failed to load documents');
        
        const docs = await response.json();
        docs.forEach(doc => {
            const item = addFileToUI(doc.filename, doc.filename, '✅');
            const info = document.createElement('div');
            info.style.fontSize = '10px';
            info.style.color = '#555';
            const date = new Date(doc.last_modified).toLocaleDateString();
            info.textContent = `In MinIO - ${date} (${(doc.size / 1024).toFixed(1)} KB)`;
            item.appendChild(info);
        });
    } catch (error) {
        console.error('Error loading documents:', error);
    }
}

// Initialize
loadDocuments();

// Meilisearch search logic
async function search() {
    const query = searchInput.value.trim();
    resultsContainer.innerHTML = '';

    if (!query) return;

    try {
        const response = await fetch(`http://localhost:8000/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Search failed');

        const results = await response.json();
        
        if (results.hits.length === 0) {
            resultsContainer.innerHTML = '<p style="color: #777;">No matches found.</p>';
            return;
        }

        results.hits.forEach(hit => {
            const resultItem = document.createElement('div');
            resultItem.className = 'result-item';
            
            // Meilisearch provides highlights in _formatted
            const snippet = hit._formatted.text;

            resultItem.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h4>${hit.filename}</h4>
                    <span style="font-size: 10px; color: #555;">ID: ${hit.id.substring(0, 8)}...</span>
                </div>
                <p>${snippet}</p>
            `;
            resultsContainer.appendChild(resultItem);
        });
    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = `<p style="color: #ff4d4d;">Error: ${error.message}</p>`;
    }
}

searchBtn.addEventListener('click', search);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') search();
});
