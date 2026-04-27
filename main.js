const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const searchInput = document.getElementById('search-input');
const searchBtn = document.getElementById('search-btn');
const resultsContainer = document.getElementById('results');

// New Preview Elements
const previewContainer = document.getElementById('preview-container');
const previewTitle = document.getElementById('preview-title');
const previewBody = document.getElementById('preview-body');
const perFileSearch = document.getElementById('per-file-search');
const findMissingBtn = document.getElementById('find-missing-btn');
const validationReport = document.getElementById('validation-report');

let documents = [];
let currentDocId = null;
let currentDocText = "";

// Drag and drop handlers
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
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
        
        // Refresh MinIO list after upload
        loadDocuments();
        
    } catch (error) {
        console.error('Error:', error);
        updateFileStatus(fileId, '❌', error.message);
    }
}

function addFileToUI(name, id, statusText, docId = null) {
    const item = document.createElement('div');
    item.className = 'file-item';
    item.id = `file-${id}`;
    item.innerHTML = `<div class="file-row"><span>${name}</span> <span class="status">${statusText}</span></div>`;
    
    if (docId) {
        item.style.cursor = 'pointer';
        item.onclick = () => selectDocument(docId, name);
    }
    
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
        const response = await fetch('http://localhost:8000/documents');
        if (!response.ok) throw new Error('Failed to load documents');
        
        const docs = await response.json();
        fileList.innerHTML = ''; // Clear list
        docs.forEach(doc => {
            const item = addFileToUI(doc.filename, doc.id, '✅', doc.id);
            const info = document.createElement('div');
            info.style.fontSize = '10px';
            info.style.color = '#555';
            const date = new Date(doc.created_at).toLocaleDateString();
            info.textContent = `Stored in DB - ${date}`;
            item.appendChild(info);
        });
    } catch (error) {
        console.error('Error loading documents:', error);
    }
}

// Select and Preview Document
async function selectDocument(docId, filename) {
    currentDocId = docId;
    previewContainer.classList.remove('hidden');
    previewTitle.textContent = `Preview: ${filename}`;
    previewBody.textContent = "Loading...";
    validationReport.classList.add('hidden');
    perFileSearch.value = '';

    try {
        const response = await fetch(`http://localhost:8000/documents/${docId}`);
        if (!response.ok) throw new Error('Failed to fetch document details');
        
        const data = await response.json();
        currentDocText = data.text;
        previewBody.textContent = currentDocText;
    } catch (error) {
        previewBody.textContent = `Error loading document: ${error.message}`;
    }
}

// Find Missing Button
findMissingBtn.onclick = async () => {
    if (!currentDocId) return;
    
    validationReport.classList.remove('hidden');
    validationReport.textContent = "Validating...";

    console.log(`Validating document: ${currentDocId}`);
    const url = `http://localhost:8000/documents/${currentDocId}/validate`;
    console.log(`Fetch URL: ${url}`);

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Server error: ${response.status}`);
        
        const data = await response.json();
        
        if (data && data.missing_fields && data.missing_fields.length > 0) {
            validationReport.innerHTML = `⚠️ <strong>Missing Fields:</strong> ${data.missing_fields.join(', ')}`;
        } else if (data && data.missing_fields) {
            validationReport.innerHTML = "✅ <strong>All fields found!</strong> Document appears complete.";
        } else {
            throw new Error("Invalid response format from server");
        }
    } catch (error) {
        console.error('Validation error:', error);
        validationReport.textContent = `Error validating: ${error.message}`;
    }
};

// Per-file Search Highlighting
perFileSearch.oninput = () => {
    const query = perFileSearch.value.trim();
    if (!query) {
        previewBody.textContent = currentDocText;
        return;
    }

    const regex = new RegExp(`(${query})`, 'gi');
    const highlighted = currentDocText.replace(regex, '<mark class="highlight">$1</mark>');
    previewBody.innerHTML = highlighted;
};

// Meilisearch search logic
async function search() {
    const query = searchInput.value.trim();
    resultsContainer.innerHTML = '';
    previewContainer.classList.add('hidden'); // Hide preview on global search

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
            resultItem.style.cursor = 'pointer';
            resultItem.onclick = () => selectDocument(hit.id, hit.filename);
            
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

// Initialize
loadDocuments();
