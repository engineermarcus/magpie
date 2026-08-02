import multiprocessing

# Workers: 2-4 per CPU core is the rule of thumb
# Keep it at 4 for a server handling streams + downloads
workers = 4

# Each worker can handle multiple requests via threads
threads = 4

# Timeout — long because /api/play can take up to 120s waiting for FFmpeg
timeout = 150

# Bind
bind = "0.0.0.0:5000"

# Logging
accesslog = "-"
errorlog  = "-"
loglevel  = "info"

# Keep connections alive for polling clients
keepalive = 5

# Worker class — sync is fine since our heavy work is in threads/subprocesses
worker_class = "sync"
