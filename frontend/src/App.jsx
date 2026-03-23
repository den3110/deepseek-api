import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ThemeProvider, createTheme, CssBaseline,
  Box, Drawer, AppBar, Toolbar, Typography, IconButton,
  List, ListItemButton, ListItemIcon, ListItemText,
  TextField, Button, Paper, Chip, Avatar, Divider,
  Tooltip, Fade, CircularProgress, Snackbar, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions
} from '@mui/material'
import {
  Add as AddIcon,
  Send as SendIcon,
  Chat as ChatIcon,
  Delete as DeleteIcon,
  Psychology as ThinkingIcon,
  Search as SearchIcon,
  Menu as MenuIcon,
  SmartToy as BotIcon,
  Person as PersonIcon,
  AttachFile as AttachIcon,
  InsertDriveFile as FileIcon,
  Close as CloseIcon,
  Image as ImageIcon,
  VpnKey as KeyIcon,
  ContentCopy as CopyIcon,
  Api as ApiIcon
} from '@mui/icons-material'
import './index.css'

const DRAWER_WIDTH = 280
const API_BASE = '/api'

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#7c4dff', light: '#b388ff' },
    background: { default: '#0f0f14', paper: '#1a1a24' },
    divider: 'rgba(255,255,255,0.08)',
  },
  typography: { fontFamily: "'Inter', -apple-system, sans-serif" },
  shape: { borderRadius: 12 },
  components: {
    MuiCssBaseline: { styleOverrides: { body: { backgroundColor: '#0f0f14' } } },
    MuiButton: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } }
  }
})

function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  return (
    <Fade in timeout={400}>
      <Box sx={{ maxWidth: 780, mx: 'auto', mb: 2.5 }}>
         <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Avatar sx={{ width: 30, height: 30, fontSize: 14, bgcolor: isUser ? 'rgba(124,77,255,0.2)' : 'primary.main' }}>
            {isUser ? <PersonIcon sx={{ fontSize: 18 }} /> : <BotIcon sx={{ fontSize: 18 }} />}
          </Avatar>
          <Typography variant="subtitle2" fontWeight={600}>{isUser ? 'You' : 'DeepSeek'}</Typography>
          {!isUser && message.elapsed && (
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, bgcolor: 'rgba(255,255,255,0.05)', px: 1, py: 0.2, borderRadius: 1 }}>
              ⏱ {message.elapsed}s
            </Typography>
          )}
        </Box>
        {message.files && message.files.length > 0 && (
          <Box sx={{ pl: '38px', mb: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {message.files.map((f, i) => (
              <Chip key={i} icon={<FileIcon sx={{ fontSize: 16 }} />} label={f.name}
                size="small" variant="outlined"
                sx={{ borderColor: 'rgba(124,77,255,0.3)', color: 'primary.light', fontSize: 12 }}
              />
            ))}
          </Box>
        )}
        {message.thinking && (
          <Paper elevation={0} sx={{ ml: '38px', mb: 1, p: 1.5, bgcolor: 'rgba(124,77,255,0.06)', borderLeft: '3px solid rgba(124,77,255,0.3)', borderRadius: '0 8px 8px 0' }}>
            <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
              <ThinkingIcon sx={{ fontSize: 14 }} /> THINKING
            </Typography>
            <Typography variant="body2" sx={{ color: 'primary.light', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{message.thinking}</Typography>
          </Paper>
        )}
        <Box sx={{ pl: '38px', fontSize: 14, lineHeight: 1.7, color: 'text.primary' }} className="markdown-content">
          {isUser ? (
            <Typography variant="body2" sx={{ lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{message.content}</Typography>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ''}</ReactMarkdown>
          )}
        </Box>
      </Box>
    </Fade>
  )
}

function ChatInput({ activeId, isStreaming, onSend, showSnack }) {
  const [input, setInput] = useState('')
  const [attachedFiles, setAttachedFiles] = useState([]) // {file, name, uploading, fileId, error}
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)

  const handleFileSelect = useCallback(async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    e.target.value = '' // reset

    for (const file of files) {
      const entry = { file, name: file.name, uploading: true, fileId: null, error: null }
      setAttachedFiles(prev => [...prev, entry])

      try {
        const formData = new FormData()
        formData.append('file', file)
        const res = await fetch(`${API_BASE}/chat/upload`, { method: 'POST', body: formData })
        const data = await res.json()

        if (data.error) throw new Error(data.error)

        setAttachedFiles(prev => prev.map(f =>
          f.file === file ? { ...f, uploading: false, fileId: data.file_id } : f
        ))
        showSnack(`✅ ${file.name} uploaded`, 'success')
      } catch (err) {
        setAttachedFiles(prev => prev.map(f =>
          f.file === file ? { ...f, uploading: false, error: err.message } : f
        ))
        showSnack(`❌ Upload failed: ${err.message}`, 'error')
      }
    }
  }, [showSnack])

  const removeFile = useCallback((index) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index))
  }, [])

  const handleSend = () => {
    if (!input.trim() || !activeId || isStreaming) return

    if (attachedFiles.some(f => f.uploading)) {
      showSnack('Please wait for files to finish uploading', 'warning')
      return
    }

    const text = input.trim()
    const fileIds = attachedFiles.filter(f => f.fileId).map(f => f.fileId)
    const fileNames = attachedFiles.filter(f => f.fileId).map(f => ({ name: f.name }))
    
    setInput('')
    setAttachedFiles([])
    onSend(text, fileIds, fileNames)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <Paper elevation={0} sx={{ borderTop: 1, borderColor: 'divider', bgcolor: 'background.paper' }}>
      {/* Attached files preview */}
      {attachedFiles.length > 0 && (
        <Box sx={{ px: 3, pt: 1.5, maxWidth: 780, mx: 'auto', display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {attachedFiles.map((f, i) => (
            <Chip
              key={i}
              icon={f.uploading ? <CircularProgress size={14} /> : f.error ? null : <FileIcon sx={{ fontSize: 16 }} />}
              label={f.uploading ? `Uploading ${f.name}...` : f.error ? `❌ ${f.name}` : `📎 ${f.name}`}
              size="small"
              onDelete={() => removeFile(i)}
              deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
              variant="outlined"
              color={f.error ? 'error' : f.fileId ? 'success' : 'default'}
              sx={{ fontSize: 12 }}
            />
          ))}
        </Box>
      )}

      <Box sx={{ p: 2, maxWidth: 780, mx: 'auto', display: 'flex', gap: 1.5, alignItems: 'flex-end' }}>
        {/* Hidden file input */}
        <input ref={fileInputRef} type="file" multiple hidden onChange={handleFileSelect}
          accept=".txt,.pdf,.doc,.docx,.xls,.xlsx,.csv,.json,.py,.js,.ts,.html,.css,.md,.xml,.yaml,.yml,.png,.jpg,.jpeg,.gif,.webp" />

        {/* Attach button */}
        <Tooltip title="Attach file">
          <span>
            <IconButton
              onClick={() => fileInputRef.current?.click()}
              disabled={!activeId || isStreaming}
              sx={{ color: 'text.secondary', '&:hover': { color: 'primary.light', bgcolor: 'rgba(124,77,255,0.1)' } }}
            >
              <AttachIcon />
            </IconButton>
          </span>
        </Tooltip>

        <TextField inputRef={inputRef} fullWidth multiline maxRows={6}
          placeholder={activeId ? "Type a message... (Shift+Enter for new line)" : "Create a new chat first..."}
          value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
          disabled={!activeId || isStreaming} variant="outlined" size="small"
          sx={{ '& .MuiOutlinedInput-root': { bgcolor: 'rgba(255,255,255,0.03)',
            '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'primary.main' } } }} />

        <Tooltip title="Send">
          <span>
            <IconButton color="primary" onClick={handleSend}
              disabled={!input.trim() || !activeId || isStreaming}
              sx={{ bgcolor: 'primary.main', color: '#fff', width: 42, height: 42,
                '&:hover': { bgcolor: 'primary.dark', transform: 'translateY(-1px)' },
                '&:disabled': { bgcolor: 'rgba(124,77,255,0.2)', color: 'rgba(255,255,255,0.3)' },
                transition: 'all 0.2s' }}>
              <SendIcon sx={{ fontSize: 20 }} />
            </IconButton>
          </span>
        </Tooltip>
      </Box>
    </Paper>
  )
}

export default function App() {
  const [sessions, setSessions] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dsk_sessions') || '[]') } catch { return [] }
  })
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dsk_messages') || '{}') } catch { return {} }
  })
  const [isStreaming, setIsStreaming] = useState(false)
  const [thinkingElapsed, setThinkingElapsed] = useState(0)
  const thinkingTimerRef = useRef(null)
  const thinkingStartRef = useRef(null)
  const hasReceivedContent = useRef(false)
  const [thinkingOn, setThinkingOn] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dsk_thinking') || 'false') } catch { return false }
  })
  const [searchOn, setSearchOn] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dsk_search') || 'false') } catch { return false }
  })
  const [useOpenAI, setUseOpenAI] = useState(() => {
    try { return JSON.parse(localStorage.getItem('dsk_openai_mode') || 'false') } catch { return false }
  })
  const [mobileOpen, setMobileOpen] = useState(false)
  const [snackbar, setSnackbar] = useState({ open: false, msg: '', severity: 'info' })
  const [keysOpen, setKeysOpen] = useState(false)
  const [apiKeys, setApiKeys] = useState([])
  const endRef = useRef(null)

  useEffect(() => { localStorage.setItem('dsk_sessions', JSON.stringify(sessions)) }, [sessions])
  useEffect(() => { localStorage.setItem('dsk_messages', JSON.stringify(messages)) }, [messages])
  useEffect(() => { localStorage.setItem('dsk_thinking', JSON.stringify(thinkingOn)) }, [thinkingOn])
  useEffect(() => { localStorage.setItem('dsk_search', JSON.stringify(searchOn)) }, [searchOn])
  useEffect(() => { localStorage.setItem('dsk_openai_mode', JSON.stringify(useOpenAI)) }, [useOpenAI])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, activeId])

  const showSnack = (msg, severity = 'info') => setSnackbar({ open: true, msg, severity })

  const createChat = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/chat/sessions`, { method: 'POST' })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      const s = { id: data.session_id, title: 'New Chat', ts: Date.now() }
      setSessions(prev => [s, ...prev])
      setActiveId(data.session_id)
      setMessages(prev => ({ ...prev, [data.session_id]: [] }))
      setMobileOpen(false)
    } catch (err) { showSnack('Failed to create chat: ' + err.message, 'error') }
  }, [])

  const deleteChat = useCallback((id) => {
    setSessions(prev => prev.filter(s => s.id !== id))
    setMessages(prev => { const c = { ...prev }; delete c[id]; return c })
    if (activeId === id) setActiveId(null)
  }, [activeId])

  // API Key Management
  const loadKeys = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/keys`)
      const data = await res.json()
      setApiKeys(data.keys || [])
    } catch (err) { console.error('Failed to load keys', err) }
  }, [])

  const generateKey = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/keys/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      const data = await res.json()
      setApiKeys(prev => [{ key: data.key, name: data.name, created_at: new Date().toISOString() }, ...prev])
      showSnack('Key generated successfully', 'success')
    } catch (err) { showSnack('Failed to generate key', 'error') }
  }, [])

  const deleteKey = useCallback(async (keyId) => {
    try {
      await fetch(`${API_BASE}/keys/${keyId}`, { method: 'DELETE' })
      setApiKeys(prev => prev.filter(k => k.key !== keyId))
      showSnack('Key deleted', 'success')
    } catch (err) { showSnack('Failed to delete key', 'error') }
  }, [])

  useEffect(() => {
    loadKeys()
  }, [loadKeys])

  const sendMessage = useCallback(async (text, fileIds, fileNames) => {
    const userMsg = { role: 'user', content: text, files: fileNames }
    const botMsg = { role: 'assistant', content: '', thinking: '' }

    setMessages(prev => ({
      ...prev,
      [activeId]: [...(prev[activeId] || []), userMsg, botMsg]
    }))

    if (!(messages[activeId]?.length)) {
      setSessions(prev => prev.map(s =>
        s.id === activeId ? { ...s, title: text.slice(0, 50) } : s
      ))
    }

    setIsStreaming(true)
    hasReceivedContent.current = false
    thinkingStartRef.current = Date.now()
    setThinkingElapsed(0)
    thinkingTimerRef.current = setInterval(() => {
      setThinkingElapsed(((Date.now() - thinkingStartRef.current) / 1000).toFixed(1))
    }, 100)

    try {
      let res;
      if (useOpenAI) {
        // Prepare OpenAI messages
        const history = (messages[activeId] || []).map(m => ({ role: m.role, content: m.content }))
        const openAiMsgs = [...history, { role: 'user', content: text }]
        let apiKey = apiKeys.length > 0 ? apiKeys[0].key : 'sk-dummy'
        
        res = await fetch(`/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${apiKey}` },
          body: JSON.stringify({
            model: 'deepseek-chat',
            messages: openAiMsgs,
            stream: true
          })
        })
      } else {
        // DeepSeek Web API format
        // Find parent_message_id from the last COMPLETED assistant message
        const currentMsgs = messages[activeId] || []
        let parentId = null
        for (let i = currentMsgs.length - 1; i >= 0; i--) {
          if (currentMsgs[i].role === 'assistant' && currentMsgs[i].message_id) {
            parentId = currentMsgs[i].message_id
            break
          }
        }


        res = await fetch(`${API_BASE}/chat/send`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: activeId,
            prompt: text,
            parent_message_id: parentId,
            thinking_enabled: thinkingOn,
            search_enabled: searchOn,
            ref_file_ids: fileIds,
          })
        })
      }

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}))
        throw new Error(errJson.error?.message || errJson.error || 'Request failed')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (dataStr === '[DONE]') continue
          
          try {
            const chunk = JSON.parse(dataStr)
            
            // Stop thinking timer on first real content
            if (!hasReceivedContent.current) {
              const hasContent = useOpenAI
                ? (chunk.choices?.[0]?.delta?.content || chunk.choices?.[0]?.delta?.reasoning_content)
                : (chunk.content && (chunk.type === 'text' || chunk.type === 'thinking'))
              if (hasContent) {
                hasReceivedContent.current = true
                if (thinkingTimerRef.current) {
                  clearInterval(thinkingTimerRef.current)
                  thinkingTimerRef.current = null
                }
                const finalElapsed = ((Date.now() - thinkingStartRef.current) / 1000).toFixed(1)
                setThinkingElapsed(finalElapsed)
                // Save elapsed time into the bot message
                setMessages(prev => {
                  const msgs = [...(prev[activeId] || [])]
                  const last = { ...msgs[msgs.length - 1] }
                  last.elapsed = finalElapsed
                  msgs[msgs.length - 1] = last
                  return { ...prev, [activeId]: msgs }
                })
              }
            }

            setMessages(prev => {
              const msgs = [...(prev[activeId] || [])]
              const last = { ...msgs[msgs.length - 1] }
              
              if (useOpenAI) {
                const delta = chunk.choices?.[0]?.delta || {}
                if (delta.reasoning_content) last.thinking = (last.thinking || '') + delta.reasoning_content
                if (delta.content) last.content = (last.content || '') + delta.content
              } else {
                if (chunk.type === 'done' || chunk.type === 'error' || chunk.finish_reason === 'stop') return prev
                if (chunk.type === 'thinking') last.thinking = (last.thinking || '') + (chunk.content || '')
                else if (chunk.type === 'text') last.content = (last.content || '') + (chunk.content || '')
                if (chunk.message_id) last.message_id = chunk.message_id
              }
              
              msgs[msgs.length - 1] = last
              return { ...prev, [activeId]: msgs }
            })
          } catch {}
        }
      }
    } catch (err) {
      setMessages(prev => {
        const msgs = [...(prev[activeId] || [])]
        const last = { ...msgs[msgs.length - 1] }
        last.content = `❌ Connection error: ${err.message}`
        msgs[msgs.length - 1] = last
        return { ...prev, [activeId]: msgs }
      })
    } finally {
      setIsStreaming(false)
      if (thinkingTimerRef.current) {
        clearInterval(thinkingTimerRef.current)
        thinkingTimerRef.current = null
      }
    }
  }, [activeId, thinkingOn, searchOn, messages, useOpenAI, apiKeys])

  const currentMsgs = messages[activeId] || []

  const drawer = (
    <>
      <Box sx={{ p: 2.5, borderBottom: 1, borderColor: 'divider', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h6" fontWeight={700} sx={{
            background: 'linear-gradient(135deg, #b388ff, #7c4dff)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent'
          }}>DeepSeek Chat</Typography>
          <Typography variant="caption" color="text.secondary">Free API Interface</Typography>
        </Box>
        <Tooltip title="API Keys">
          <IconButton size="small" onClick={() => setKeysOpen(true)} sx={{ color: 'text.secondary', '&:hover': { color: 'primary.light' } }}>
            <KeyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      <Box sx={{ p: 1.5 }}>
        <Button variant="contained" fullWidth startIcon={<AddIcon />} onClick={createChat}
          sx={{ py: 1.2, background: 'linear-gradient(135deg, #7c4dff, #5a3dd1)',
            boxShadow: '0 2px 12px rgba(124,77,255,0.3)',
            '&:hover': { boxShadow: '0 4px 20px rgba(124,77,255,0.4)', transform: 'translateY(-1px)' },
            transition: 'all 0.2s' }}>New Chat</Button>
      </Box>
      <List sx={{ flex: 1, overflow: 'auto', px: 1 }}>
        {sessions.map(s => (
          <ListItemButton key={s.id} selected={s.id === activeId}
            onClick={() => { setActiveId(s.id); setMobileOpen(false); }}
            sx={{ borderRadius: 2, mb: 0.3, '&.Mui-selected': { bgcolor: 'rgba(124,77,255,0.12)' } }}>
            <ListItemIcon sx={{ minWidth: 36 }}><ChatIcon sx={{ fontSize: 18, opacity: 0.6 }} /></ListItemIcon>
            <ListItemText primary={s.title || 'New Chat'} primaryTypographyProps={{ fontSize: 13, noWrap: true }} />
            <IconButton size="small" onClick={e => { e.stopPropagation(); deleteChat(s.id) }}
              sx={{ opacity: 0, '.MuiListItemButton-root:hover &': { opacity: 1 } }}>
              <DeleteIcon sx={{ fontSize: 16 }} />
            </IconButton>
          </ListItemButton>
        ))}
      </List>
      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Paper elevation={0} sx={{ p: 1, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: 2, border: 1, borderColor: 'divider' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography variant="body2" fontWeight={600} display="flex" alignItems="center" gap={1}>
              <ApiIcon sx={{ fontSize: 16, color: useOpenAI ? 'success.main' : 'text.secondary' }} /> /v1 Mode
            </Typography>
            <Chip 
              label={useOpenAI ? "ON" : "OFF"} 
              size="small"
              onClick={() => setUseOpenAI(!useOpenAI)}
              color={useOpenAI ? "success" : "default"}
              sx={{ height: 20, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
            />
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.3 }}>
            {useOpenAI ? "Using generic OpenAI standard interface." : "Using DeepSeek Web Sessions."}
          </Typography>
        </Paper>
      </Box>
    </>
  )

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', height: '100vh' }}>
        <Drawer variant="permanent" sx={{ width: DRAWER_WIDTH, display: { xs: 'none', md: 'block' },
          '& .MuiDrawer-paper': { width: DRAWER_WIDTH, bgcolor: 'background.paper', borderRight: '1px solid', borderColor: 'divider' } }}>
          {drawer}
        </Drawer>
        <Drawer variant="temporary" open={mobileOpen} onClose={() => setMobileOpen(false)}
          sx={{ display: { xs: 'block', md: 'none' }, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, bgcolor: 'background.paper' } }}>
          {drawer}
        </Drawer>

        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <AppBar position="static" elevation={0} sx={{ bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider' }}>
            <Toolbar sx={{ gap: 1 }}>
              <IconButton edge="start" onClick={() => setMobileOpen(true)} sx={{ display: { md: 'none' } }}><MenuIcon /></IconButton>
              <Typography variant="subtitle1" fontWeight={600} sx={{ flex: 1 }} noWrap>
                {sessions.find(s => s.id === activeId)?.title || 'DeepSeek Chat'}
              </Typography>
              <Chip icon={<ThinkingIcon sx={{ fontSize: 16 }} />} label="Thinking" size="small"
                variant={thinkingOn ? 'filled' : 'outlined'} color={thinkingOn ? 'primary' : 'default'}
                onClick={() => setThinkingOn(!thinkingOn)} sx={{ cursor: 'pointer' }} />
              <Chip icon={<SearchIcon sx={{ fontSize: 16 }} />} label="Search" size="small"
                variant={searchOn ? 'filled' : 'outlined'} color={searchOn ? 'primary' : 'default'}
                onClick={() => setSearchOn(!searchOn)} sx={{ cursor: 'pointer' }} />
            </Toolbar>
          </AppBar>

          {/* Messages */}
          <Box sx={{ flex: 1, overflow: 'auto', p: 3 }}>
            {!activeId ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2, opacity: 0.7 }}>
                <Typography fontSize={56}>🚀</Typography>
                <Typography variant="h5" fontWeight={700}>Welcome to DeepSeek Chat</Typography>
                <Typography variant="body2" color="text.secondary" textAlign="center" maxWidth={400}>
                  Click "New Chat" to start. Supports file upload, thinking mode, and web search.
                </Typography>
              </Box>
            ) : currentMsgs.length === 0 ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 2, opacity: 0.7 }}>
                <Typography fontSize={48}>💬</Typography>
                <Typography variant="h6" fontWeight={600}>Start chatting</Typography>
                <Typography variant="body2" color="text.secondary">Type a message or attach a file below.</Typography>
              </Box>
            ) : (
              <>
                {currentMsgs.map((msg, i) => <ChatMessage key={i} message={msg} />)}
                {isStreaming && !hasReceivedContent.current && (
                  <Fade in timeout={300}>
                    <Box sx={{ pl: '38px', maxWidth: 780, mx: 'auto', display: 'flex', alignItems: 'center', gap: 1.5 }}>
                      <CircularProgress size={16} sx={{ color: 'primary.light' }} />
                      <Typography variant="body2" sx={{ color: 'primary.light', fontSize: 13, fontWeight: 500 }}>
                        Đang suy nghĩ... {thinkingElapsed}s
                      </Typography>
                    </Box>
                  </Fade>
                )}
              </>
            )}
            <div ref={endRef} />
          </Box>

          {/* Input */}
          <ChatInput 
            key={activeId || 'empty'}
            activeId={activeId}
            isStreaming={isStreaming}
            onSend={sendMessage}
            showSnack={showSnack}
          />
        </Box>
      </Box>

      <Snackbar open={snackbar.open} autoHideDuration={3000} onClose={() => setSnackbar(p => ({ ...p, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity={snackbar.severity} variant="filled" onClose={() => setSnackbar(p => ({ ...p, open: false }))}>
          {snackbar.msg}
        </Alert>
      </Snackbar>

      {/* API Key Dialog */}
      <Dialog open={keysOpen} onClose={() => setKeysOpen(false)} maxWidth="sm" fullWidth
        PaperProps={{ sx: { bgcolor: 'background.paper', backgroundImage: 'none', borderRadius: 3 } }}>
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1 }}>
          <Typography variant="h6" fontWeight={600} display="flex" alignItems="center" gap={1}>
            <KeyIcon color="primary" /> API Keys
          </Typography>
          <IconButton onClick={() => setKeysOpen(false)} size="small"><CloseIcon /></IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'divider', p: 0 }}>
          <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: 'rgba(255,255,255,0.02)' }}>
            <Typography variant="body2" color="text.secondary">
              Use these keys for the /v1/chat/completions endpoint.
            </Typography>
            <Button variant="contained" size="small" onClick={generateKey} startIcon={<AddIcon />}>
              Generate Key
            </Button>
          </Box>
          <List sx={{ pt: 0 }}>
            {apiKeys.length === 0 ? (
              <Box sx={{ p: 4, textAlign: 'center', opacity: 0.5 }}>
                <Typography variant="body2">No API keys found.</Typography>
              </Box>
            ) : apiKeys.map(k => (
              <Box key={k.key}>
                <Divider sx={{ borderColor: 'divider' }} />
                <Box sx={{ px: 3, py: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                  <Box>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', color: 'primary.light', mb: 0.5 }}>
                      {k.key}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Created: {new Date(k.created_at.replace(' ', 'T') + (k.created_at.endsWith('Z') ? '' : 'Z')).toLocaleString()}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Tooltip title="Copy">
                      <IconButton size="small" onClick={() => { navigator.clipboard.writeText(k.key); showSnack('Copied to clipboard', 'success'); }}>
                        <CopyIcon sx={{ fontSize: 18 }} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton size="small" color="error" onClick={() => deleteKey(k.key)}>
                        <DeleteIcon sx={{ fontSize: 18 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Box>
            ))}
          </List>
        </DialogContent>
      </Dialog>
    </ThemeProvider>
  )
}
