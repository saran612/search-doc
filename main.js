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
    // Create a temporary item in the list
    const fileId = Date.now();
    const item = document.createElement('div');
    item.className = 'file-item';
    item.id = `file-${fileId}`;
    item.innerHTML = `<div class="file-row"><span>${file.name}</span> <span class="status">Uploading...</span></div>`;
    fileList.appendChild(item);

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
        item.querySelector('.status').textContent = '✅';
        
        // Show storage info
        const info = document.createElement('div');
        info.style.fontSize = '10px';
        info.style.color = '#555';
        info.textContent = `Stored in ${data.storage} (${data.bucket})`;
        item.appendChild(info);
        
        // Add to our local document store
        documents.push({
            name: data.filename,
            text: data.text,
            id: fileId
        });

    } catch (error) {
        console.error('Error:', error);
        item.querySelector('.status').textContent = '❌';
        item.title = error.message;
    }
}

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
