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
const analyzeBtn = document.getElementById('analyze-btn');
const validationReport = document.getElementById('validation-report');
const analysisReport = document.getElementById('analysis-report');
const analysisPanel = document.getElementById('analysis-panel');

let documents = [];
let currentDocId = null;
let currentDocText = "";

// Configure Backend URL based on environment
const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
// IMPORTANT: Replace the placeholder below with your actual Render URL!
const API_BASE_URL = (isLocal ? 'http://localhost:8000' : 'https://search-doc.onrender.com').replace(/\/+$/, '');

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
        const response = await fetch(`${API_BASE_URL}/upload`, {
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
        item.onclick = () => selectDocument(docId, name, true);
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
        const response = await fetch(`${API_BASE_URL}/documents`);
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
async function selectDocument(docId, filename, fromSidebar = false) {
    if (fromSidebar) {
        resultsContainer.innerHTML = '';
        searchInput.value = '';
    }
    
    currentDocId = docId;
    previewContainer.classList.remove('hidden');
    previewTitle.textContent = `Preview: ${filename}`;
    previewBody.textContent = "Loading...";
    validationReport.classList.add('hidden');
    analysisReport.classList.add('hidden');
    analysisPanel.classList.add('hidden');
    perFileSearch.value = '';

    try {
        const response = await fetch(`${API_BASE_URL}/documents/${docId}`);
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
    
    analysisPanel.classList.remove('hidden');
    validationReport.classList.remove('hidden');
    validationReport.textContent = "Validating...";

    console.log(`Validating document: ${currentDocId}`);
    const url = `${API_BASE_URL}/documents/${currentDocId}/validate`;
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

// Deep Analyze Button
analyzeBtn.onclick = async () => {
    if (!currentDocId) return;
    
    analysisPanel.classList.remove('hidden');
    analysisReport.classList.remove('hidden');
    analysisReport.innerHTML = "<strong>Analyzing document...</strong>";

    try {
        const response = await fetch(`${API_BASE_URL}/documents/${currentDocId}/analyze`);
        if (!response.ok) throw new Error(`Server error: ${response.status}`);
        
        const data = await response.json();
        
        // Build the HTML report
        let html = `<h3 style="margin-top:0; color:#28a745;">Analysis Complete</h3>`;
        
        // Category
        html += `<div style="margin-bottom: 15px;">
            <strong>Classification:</strong> <span style="background-color:#e9ecef; padding: 2px 6px; border-radius:4px;">${data.classification.category}</span>
            <br><small style="color:#666;">Confidence: ${(data.classification.confidence * 100).toFixed(0)}% | Reason: ${data.classification.reasoning}</small>
        </div>`;
        
        // Summary fields
        html += `<strong>Clinical Summary:</strong><ul style="margin-top: 5px; font-size: 14px;">`;
        for (const [key, value] of Object.entries(data.summary)) {
            html += `<li><strong>${key.replace('_', ' ')}:</strong> ${value || '<em style="color:#aaa;">null</em>'}</li>`;
        }
        html += `</ul>`;
        
        // Validation issues
        if (data.validation.is_valid && data.validation.warnings.length === 0) {
            html += `<div style="color: green;"><strong>Validation:</strong> ✅ Clean (No inconsistencies)</div>`;
        } else {
            html += `<strong>Validation Flags:</strong><ul style="margin-top: 5px; font-size: 14px;">`;
            data.validation.errors.forEach(e => html += `<li style="color: red;">❌ Error: Missing/Invalid ${e.field}</li>`);
            data.validation.warnings.forEach(w => html += `<li style="color: orange;">⚠️ Warning: ${w.detail}</li>`);
            html += `</ul>`;
        }

        analysisReport.innerHTML = html;
        
    } catch (error) {
        console.error('Analysis error:', error);
        analysisReport.innerHTML = `<span style="color:red;">Error analyzing document: ${error.message}</span>`;
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
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}`);
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

// Resizer Logic
function setupResizer(resizerId, leftElement, isSidebar = false) {
    const resizer = document.getElementById(resizerId);
    let x = 0;
    let w = 0;

    const mouseDownHandler = function (e) {
        x = e.clientX;
        const rect = leftElement.getBoundingClientRect();
        w = rect.width;

        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
        resizer.classList.add('resizing');
        document.body.classList.add('resizing');
    };

    const mouseMoveHandler = function (e) {
        const dx = e.clientX - x;
        const newWidth = w + dx;
        
        // Boundaries for sidebar
        if (isSidebar) {
            if (newWidth > 200 && newWidth < 500) {
                leftElement.style.width = `${newWidth}px`;
            }
        } else {
            // Boundaries for preview split
            const containerWidth = leftElement.parentElement.getBoundingClientRect().width;
            const percentage = (newWidth / containerWidth) * 100;
            if (percentage > 20 && percentage < 80) {
                leftElement.style.width = `${percentage}%`;
            }
        }
    };

    const mouseUpHandler = function () {
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
        resizer.classList.remove('resizing');
        document.body.classList.remove('resizing');
    };

    resizer.addEventListener('mousedown', mouseDownHandler);
}

// Initialize resizers
const sidemenu = document.querySelector('.sidemenu');
const previewLeft = document.querySelector('.preview-left');

setupResizer('sidebar-resizer', sidemenu, true);
setupResizer('split-resizer', previewLeft, false);

// Initialize
loadDocuments();
