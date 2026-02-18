// API Configuration
const API_BASE_URL = window.location.origin; // Use same origin as frontend

// State management
let currentJobId = null;
let websocket = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
// Agent role mapping for translations
const agentRoleMap = {
    'Email Strategy Planner': 'emailPlanner',
    'Tone and Style Specialist': 'toneSpecialist',
    'Grammar and Syntax Expert': 'grammarSpecialist',
    'Spelling and Word Choice Specialist': 'dictationSpecialist',
    'Response Formatter and Analysis Specialist': 'responseFormatter',
};

// Agent name to role mapping (for matching events)
const agentNameToRoleMap = {
    'email_planner': 'Email Strategy Planner',
    'tone_specialist': 'Tone and Style Specialist',
    'grammar_specialist': 'Grammar and Syntax Expert',
    'dictation_specialist': 'Spelling and Word Choice Specialist',
    'response_formatter': 'Response Formatter and Analysis Specialist',
};

let agents = [
    { name: 'email_planner', role: 'Email Strategy Planner', roleKey: 'emailPlanner', status: 'pending', thinking: null },
    { name: 'tone_specialist', role: 'Tone and Style Specialist', roleKey: 'toneSpecialist', status: 'pending', thinking: null },
    { name: 'grammar_specialist', role: 'Grammar and Syntax Expert', roleKey: 'grammarSpecialist', status: 'pending', thinking: null },
    { name: 'dictation_specialist', role: 'Spelling and Word Choice Specialist', roleKey: 'dictationSpecialist', status: 'pending', thinking: null },
    { name: 'response_formatter', role: 'Response Formatter and Analysis Specialist', roleKey: 'responseFormatter', status: 'pending', thinking: null },
];

// DOM Elements
const emailForm = document.getElementById('email-form');
const submitBtn = document.getElementById('submit-btn');
const submitText = document.getElementById('submit-text');
const submitLoader = document.getElementById('submit-loader');
const inputSection = document.getElementById('input-section');
const progressSection = document.getElementById('progress-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const errorMessage = document.getElementById('error-message');
const progressBar = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const agentList = document.getElementById('agent-list');

// Tab functionality
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tabName = btn.dataset.tab;
        switchTab(tabName);
    });
});

function switchTab(tabName) {
    // Update buttons
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');
}

// Language switcher - initialize after DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const languageSelect = document.getElementById('language-select');
    if (languageSelect && typeof currentLang !== 'undefined') {
        languageSelect.value = currentLang;
        languageSelect.addEventListener('change', (e) => {
            if (typeof setLanguage === 'function') {
                setLanguage(e.target.value);
            }
        });
    }
});

// Form submission
emailForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const subject = document.getElementById('subject').value.trim();
    const body = document.getElementById('body').value.trim();
    
    if (!subject || !body) {
        const errorMsg = typeof t === 'function' ? t('Please fill in both subject and body fields.') : 'Please fill in both subject and body fields.';
        showError(errorMsg);
        return;
    }
    
    // Get options
    const tone = document.getElementById('tone-select')?.value || 'professional';
    const translation = document.getElementById('translation-select')?.value || 'none';
    const audience = document.getElementById('audience-select')?.value || 'general';
    
    await startJob({ 
        subject, 
        body,
        tone,
        translation,
        audience,
    });
});

// Start async job
async function startJob(data) {
    try {
        // Reset UI
        resetUI();
        showProgress();
        
        // Disable form
        submitBtn.disabled = true;
        submitText.style.display = 'none';
        submitLoader.style.display = 'inline-block';
        
        // Extract email and options
        const { subject, body, tone, translation, audience } = data;
        
        // Create job with options
        const response = await fetch(`${API_BASE_URL}/api/v1/jobs/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                email: { subject, body },
                tone: tone || 'professional',
                translation: translation || 'none',
                audience: audience || 'general',
                language: currentLang,
            }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to start job');
        }
        
        const jobData = await response.json();
        currentJobId = jobData.job_id;
        
        // Connect to WebSocket
        connectToWebSocket(currentJobId);
        
    } catch (error) {
        console.error('Error starting job:', error);
        showError(error.message || 'Failed to start email improvement. Please try again.');
        resetSubmitButton();
    }
}

// Connect to WebSocket
function connectToWebSocket(jobId) {
    // Close existing connection if any
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    
    // Determine WebSocket URL (ws:// for http, wss:// for https)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/jobs/${jobId}/ws`;
    
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    websocket = new WebSocket(wsUrl);
    reconnectAttempts = 0;
    
    websocket.onopen = () => {
        console.log('WebSocket connection opened');
        reconnectAttempts = 0;
    };
    
    websocket.onmessage = (event) => {
        try {
            // FastAPI's send_json() already sends JSON, so event.data is already a string
            const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
            console.log('WebSocket message received:', data);
            handleStreamEvent(data);
        } catch (error) {
            console.error('Error parsing WebSocket message:', error, event.data);
        }
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    websocket.onclose = (event) => {
        console.log('WebSocket connection closed', event.code, event.reason);
        websocket = null;
        
        // Attempt to reconnect if job is still in progress and not explicitly closed
        if (currentJobId && event.code !== 1000 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            console.log(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`);
            setTimeout(() => {
                if (currentJobId) {
                    connectToWebSocket(currentJobId);
                }
            }, 1000 * reconnectAttempts); // Exponential backoff
        }
    };
}

// Handle stream events
function handleStreamEvent(data) {
    console.log('Received event:', data);
    console.log('Event keys:', Object.keys(data));
    console.log('agent_name:', data.agent_name, 'agent_role:', data.agent_role, 'status:', data.status);
    
    // Handle connection event
    if (data.type === 'connected') {
        console.log('Connected to WebSocket');
        return;
    }
    
    // Handle job completion
    if (data.type === 'job_complete') {
        if (websocket) {
            websocket.close();
            websocket = null;
        }
        if (data.status === 'completed') {
            setTimeout(() => {
                loadJobResults(currentJobId);
            }, 500);
        }
        return;
    }
    
    // Handle error events
    if (data.type === 'error') {
        console.error('Error event:', data.message);
        showError(data.message || 'An error occurred during processing.');
        return;
    }
    
    // Handle agent events - check for both enum objects and string values
    const hasAgentName = data.agent_name !== undefined && data.agent_name !== null;
    const hasAgentRole = data.agent_role !== undefined && data.agent_role !== null;
    
    console.log('Event check - hasAgentName:', hasAgentName, 'hasAgentRole:', hasAgentRole);
    
    if (hasAgentName && hasAgentRole) {
        console.log('Processing agent event...');
        updateAgentStatus(data);
        
        // Update progress if available
        if (data.progress !== undefined && data.progress !== null) {
            console.log('Updating progress to:', data.progress);
            updateProgress(data.progress);
        }
        
        // Check if job is complete (system agent completed)
        const agentName = data.agent_name?.value || data.agent_name;
        const status = data.status?.value || data.status;
        
        if (status === 'completed' && agentName === 'system') {
            setTimeout(() => {
                loadJobResults(currentJobId);
            }, 1000);
        }
        
        // Handle errors
        if (status === 'failed' || status === 'FAILED') {
            if (websocket) {
                websocket.close();
                websocket = null;
            }
            showError(data.message || 'An error occurred during processing.');
        }
    } else {
        console.warn('Event missing agent_name or agent_role:', { 
            agent_name: data.agent_name, 
            agent_role: data.agent_role,
            allKeys: Object.keys(data)
        });
    }
}

// Update agent status
function updateAgentStatus(eventData) {
    console.log('updateAgentStatus called with:', eventData);
    
    // Handle both enum values and string values (enums are now serialized as strings)
    const status = eventData.status?.value || eventData.status || '';
    const agentName = eventData.agent_name?.value || eventData.agent_name || '';
    const agentRole = eventData.agent_role?.value || eventData.agent_role || '';
    const thinking = eventData.thinking || null;
    
    console.log('Extracted values:', { status, agentName, agentRole, thinking });
    
    // Skip SYSTEM events - they're not part of the agent list
    if (agentName === 'system' || agentRole === 'System') {
        console.log('Skipping SYSTEM event:', { agentName, agentRole, status });
        return;
    }
    
    console.log('Updating agent status:', { agentName, agentRole, status, thinking });
    console.log('Available agents:', agents.map(a => ({ name: a.name, role: a.role })));
    
    // Try multiple matching strategies
    let agent = agents.find(a => 
        a.name === agentName || 
        a.role === agentRole
    );
    
    // If not found, try case-insensitive matching
    if (!agent) {
        agent = agents.find(a => 
            a.name.toLowerCase() === agentName.toLowerCase() || 
            a.role.toLowerCase() === agentRole.toLowerCase()
        );
    }
    
    // If still not found, try matching by agent name mapping
    if (!agent && agentName && agentNameToRoleMap[agentName]) {
        const mappedRole = agentNameToRoleMap[agentName];
        agent = agents.find(a => a.role === mappedRole);
    }
    
    // If still not found, try partial role matching
    if (!agent && agentRole) {
        agent = agents.find(a => 
            agentRole.toLowerCase().includes(a.role.toLowerCase()) ||
            a.role.toLowerCase().includes(agentRole.toLowerCase())
        );
    }
    
    if (agent) {
        const statusLower = status.toLowerCase();
        console.log('Status (lowercase):', statusLower);
        
        if (statusLower === 'completed') {
            agent.status = 'completed';
        } else if (statusLower === 'started') {
            // When agent starts, show "started" status to indicate it has begun
            agent.status = 'started';
        } else if (statusLower === 'processing') {
            agent.status = 'active';
        } else {
            agent.status = 'pending';
        }
        
        // Update thinking if provided
        if (thinking) {
            agent.thinking = thinking;
        }
        
        console.log(`Agent ${agent.role} status updated to: ${agent.status}`, thinking ? 'with thinking' : '');
        renderAgentList();
    } else {
        console.warn('Agent not found:', { 
            agentName, 
            agentRole, 
            availableAgents: agents.map(a => ({ name: a.name, role: a.role })) 
        });
    }
}

// Render agent list
function renderAgentList() {
    agentList.innerHTML = '';
    
    agents.forEach((agent, index) => {
        const item = document.createElement('div');
        item.className = `agent-item ${agent.status}`;
        
        const content = document.createElement('div');
        content.className = 'agent-item-content';
        
        const statusIcon = document.createElement('div');
        statusIcon.className = `agent-status ${agent.status}`;
        
        const info = document.createElement('div');
        info.className = 'agent-info';
        
        const name = document.createElement('div');
        name.className = 'agent-name';
        // Translate agent role if translation function is available
        if (typeof t === 'function' && agent.roleKey) {
            name.textContent = t(agent.roleKey) || agent.role;
        } else {
            name.textContent = agent.role;
        }
        
        const message = document.createElement('div');
        message.className = 'agent-message';
        
        if (agent.status === 'pending') {
            message.textContent = t('waiting');
        } else if (agent.status === 'started') {
            message.textContent = t('started');
        } else if (agent.status === 'active') {
            message.textContent = t('processing');
        } else if (agent.status === 'completed') {
            message.textContent = t('completed');
        }
        
        info.appendChild(name);
        info.appendChild(message);
        content.appendChild(statusIcon);
        content.appendChild(info);
        item.appendChild(content);
        
        // Add thinking dropdown if thinking exists (for started, active or completed agents)
        // Don't show thinking for response_formatter (last agent)
        if (agent.thinking && (agent.status === 'started' || agent.status === 'active' || agent.status === 'completed') && agent.name !== 'response_formatter') {
            const thinkingContainer = document.createElement('div');
            thinkingContainer.className = 'thinking-container';
            
            const thinkingToggle = document.createElement('button');
            thinkingToggle.className = 'thinking-toggle';
            thinkingToggle.type = 'button';
            thinkingToggle.innerHTML = `<span>${t('showThinking')}</span> <span class="thinking-arrow">▼</span>`;
            
            const thinkingContent = document.createElement('div');
            thinkingContent.className = 'thinking-content';
            // Render thinking as markdown/HTML
            thinkingContent.innerHTML = marked.parse(agent.thinking || '');
            
            let isExpanded = false;
            thinkingToggle.addEventListener('click', () => {
                isExpanded = !isExpanded;
                thinkingContent.classList.toggle('show', isExpanded);
                thinkingToggle.innerHTML = `<span>${isExpanded ? t('hideThinking') : t('showThinking')}</span> <span class="thinking-arrow">${isExpanded ? '▲' : '▼'}</span>`;
            });
            
            thinkingContainer.appendChild(thinkingToggle);
            thinkingContainer.appendChild(thinkingContent);
            item.appendChild(thinkingContainer);
        }
        
        agentList.appendChild(item);
    });
}

// Update progress bar
function updateProgress(progress) {
    progressBar.style.width = `${progress}%`;
    progressText.textContent = `${Math.round(progress)}%`;
}

// Load job results
async function loadJobResults(jobId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/status`);
        if (!response.ok) {
            throw new Error('Failed to load results');
        }
        
        const jobStatus = await response.json();
        
        if (jobStatus.status === 'completed' && jobStatus.result) {
            displayResults(jobStatus.result);
        } else if (jobStatus.status === 'failed') {
            showError(jobStatus.error || 'Job failed');
        }
        
    } catch (error) {
        console.error('Error loading results:', error);
        showError('Failed to load results. Please check the job status.');
    }
}

// Display results
function displayResults(result) {
    // Hide progress, show results
    progressSection.style.display = 'none';
    resultsSection.style.display = 'block';
    
    // Display email
    document.getElementById('result-subject').textContent = result.email.subject;
    document.getElementById('result-body').textContent = result.email.body;
    
    // Display suggestions
    const suggestionsList = document.getElementById('suggestions-list');
    suggestionsList.innerHTML = '';
    result.suggestions.forEach(suggestion => {
        const li = document.createElement('li');
        li.textContent = suggestion;
        suggestionsList.appendChild(li);
    });
    
    // Display differences
    const differencesList = document.getElementById('differences-list');
    differencesList.innerHTML = '';
    result.differences.forEach(difference => {
        const li = document.createElement('li');
        li.textContent = difference;
        differencesList.appendChild(li);
    });
    
    // Reset submit button
    resetSubmitButton();
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Copy email button
document.getElementById('copy-btn').addEventListener('click', () => {
    const subject = document.getElementById('result-subject').textContent;
    const body = document.getElementById('result-body').textContent;
    const emailText = `Subject: ${subject}\n\n${body}`;
    
    navigator.clipboard.writeText(emailText).then(() => {
        const btn = document.getElementById('copy-btn');
        const originalText = btn.textContent;
        btn.textContent = t('copied');
        btn.style.background = '#10b981';
        setTimeout(() => {
            btn.textContent = originalText;
            btn.style.background = '';
        }, 2000);
    });
});

// UI Helper Functions
function showProgress() {
    inputSection.style.display = 'none';
    progressSection.style.display = 'block';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
    
    // Reset agents
    resetAgents();
    renderAgentList();
    updateProgress(0);
}

function showError(message) {
    errorMessage.textContent = message;
    errorSection.style.display = 'block';
    progressSection.style.display = 'none';
    resultsSection.style.display = 'none';
    resetSubmitButton();
}

function resetUI() {
    progressSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
    inputSection.style.display = 'block';
    currentJobId = null;
    
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    reconnectAttempts = 0;
}

function resetSubmitButton() {
    submitBtn.disabled = false;
    submitText.style.display = 'inline';
    submitLoader.style.display = 'none';
}

function resetForm() {
    resetUI();
    emailForm.reset();
}

// Initialize
if (typeof renderAgentList === 'function') {
    renderAgentList();
}

// Reset agents thinking on new job
function resetAgents() {
    agents.forEach(agent => {
        agent.status = 'pending';
        agent.thinking = null;
    });
}
