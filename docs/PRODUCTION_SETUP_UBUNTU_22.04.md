# Production Server Setup Guide (Ubuntu 22.04)

This guide covers deploying the Smart Attendance System on Ubuntu 22.04 for production use.

## Prerequisites

- Ubuntu 22.04 LTS server (minimum 2 vCPUs, 4GB RAM)
- Root or sudo access
- Domain name (optional but recommended)
- Static IP address

## Step 1: System Updates

```bash
sudo apt update
sudo apt upgrade -y
```

## Step 2: Install Dependencies

```bash
# Install Python 3.10+ and development tools
sudo apt install -y python3.10 python3.10-venv python3-pip build-essential libpq-dev redis-server nginx certbot python3-certbot-nginx git

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start and enable services
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

## Step 3: Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE attendance_db;
CREATE USER attendance WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE attendance_db TO attendance;
\q
```

## Step 4: Clone Repository

```bash
cd /opt
sudo git clone https://github.com/your-repo/smart-attendance.git
cd smart-attendance
```

## Step 5: Setup Backend Environment

```bash
cd backend

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit environment file
nano .env
```

### Required Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://attendance:your_secure_password@localhost:5432/attendance_db

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your_random_secret_key_here
ACCESS_TOKEN_EXPIRE_HOURS=8

# AWS S3 (optional - for snapshots)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
AWS_S3_BUCKET=attendance-snapshots
```

Generate a secure SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 6: Initialize Database

```bash
cd backend
source venv/bin/activate

# Run migrations
alembic upgrade head

# Create admin user
python3 -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import User
from app.core.security import get_password_hash

async def create_admin():
    engine = create_async_engine('postgresql+asyncpg://attendance:your_secure_password@localhost:5432/attendance_db')
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from app.db.base import Base
        async with session.begin():
            await session.execute(Base.metadata.create_all)

        user = User(
            email='admin@yourdomain.com',
            hashed_password=get_password_hash('admin123'),
            full_name='System Administrator',
            role='super_admin',
            is_active=True
        )
        session.add(user)
        await session.commit()
        print('✅ Admin user created: admin@yourdomain.com / admin123')

asyncio.run(create_admin())
```

## Step 7: Setup Frontend Environment

```bash
cd ../frontend

# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Edit environment file
nano .env
```

### Required Environment Variables

```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

## Step 8: Setup Celery Workers

```bash
cd backend

# Create worker virtual environment
python3.10 -m venv venv_workers
source venv_workers/bin/activate

# Install worker dependencies
pip install -r requirements.txt
pip install celery[redis]

# Create systemd service
sudo nano /etc/systemd/system/celery-worker.service
```

### Celery Worker Service File

```ini
[Unit]
Description=Celery Worker for Smart Attendance
After=network.target redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=/opt/smart-attendance/backend
Environment="PATH=/opt/smart-attendance/backend/venv_workers/bin"
ExecStart=/opt/smart-attendance/backend/venv_workers/bin/celery -A app.workers.celery_app worker --loglevel=info
Restart=always

[Install]
WantedBy=multi-user.target
```

### Enable Celery Worker

```bash
sudo systemctl daemon-reload
sudo systemctl start celery-worker
sudo systemctl enable celery-worker
```

## Step 9: Setup Nginx

```bash
# Create Nginx configuration
sudo nano /etc/nginx/sites-available/attendance
```

### Nginx Configuration

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    listen [::]:80;
    server_name api.yourdomain.com www.yourdomain.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # API requests
    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files (if served by backend)
    location /static/ {
        alias /opt/smart-attendance/backend/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Health check
    location /health {
        proxy_pass http://backend/health;
        access_log off;
    }
}
```

### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/attendance /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Step 10: Setup SSL with Certbot

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d api.yourdomain.com -d www.yourdomain.com

# Auto-renewal is configured automatically
sudo systemctl status certbot.timer
```

## Step 11: Setup Systemd Services

```bash
# Backend service
sudo nano /etc/systemd/system/attendance-backend.service
```

### Backend Service File

```ini
[Unit]
Description=Smart Attendance Backend API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/smart-attendance/backend
Environment="PATH=/opt/smart-attendance/backend/venv/bin"
ExecStart=/opt/smart-attendance/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start Backend

```bash
sudo systemctl daemon-reload
sudo systemctl start attendance-backend
sudo systemctl enable attendance-backend
sudo systemctl status attendance-backend
```

## Step 12: Configure Firewall

```bash
# UFW configuration
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Check status
sudo ufw status
```

## Step 13: Setup Monitoring (Optional)

```bash
# Install Prometheus and Grafana
sudo apt install -y prometheus prometheus-pushgateway grafana

# Configure Prometheus
sudo nano /etc/prometheus/prometheus.yml
```

### Prometheus Configuration

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'attendance-api'
    static_configs:
      - targets: ['localhost:8000']
```

### Start Services

```bash
sudo systemctl start prometheus
sudo systemctl start grafana-server
```

## Step 14: Verification

```bash
# Check all services
sudo systemctl status attendance-backend
sudo systemctl status celery-worker
sudo systemctl status nginx
sudo systemctl status postgresql
sudo systemctl status redis-server

# Test API
curl https://api.yourdomain.com/health

# Test SSL
curl -I https://api.yourdomain.com
```

## Step 15: Backup Configuration

```bash
# Create backup directory
sudo mkdir -p /opt/backups

# Set up daily backups
sudo crontab -e

# Add to crontab:
# 0 2 * * * /opt/smart-attendance/scripts/backup.sh
```

## Security Best Practices

1. **Change default passwords** immediately after deployment
2. **Use strong SECRET_KEY** (generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`)
3. **Enable HTTPS** with valid SSL certificates
4. **Configure firewall** to only allow necessary ports
5. **Regular updates** for all packages
6. **Monitor logs** regularly
7. **Set up backups** with retention policy
8. **Use environment variables** for sensitive data
9. **Enable rate limiting** in production
10. **Configure CORS** properly

## Troubleshooting

### Backend won't start
```bash
sudo journalctl -u attendance-backend -f
```

### Celery worker not running
```bash
sudo journalctl -u celery-worker -f
```

### Database connection issues
```bash
sudo -u postgres psql
\l
\c attendance_db
SELECT * FROM pg_stat_activity;
```

### Redis connection issues
```bash
redis-cli ping
```

## Performance Tuning

### Backend Configuration
Edit `backend/app/main.py`:
```python
app = FastAPI(
    title="Smart Attendance API",
    version="1.1.0",
    lifespan=lifespan,
    workers=4,  # Adjust based on CPU cores
)
```

### Nginx Configuration
- Enable gzip compression
- Configure caching headers
- Use HTTP/2 if supported
- Adjust worker_processes based on CPU cores

### Database
- Configure connection pool
- Enable query caching
- Monitor slow queries
- Regular vacuum and analyze

## Production Checklist

- [ ] All services running and healthy
- [ ] SSL certificate installed and valid
- [ ] Firewall configured
- [ ] Backups configured
- [ ] Monitoring enabled
- [ ] Logs rotated
- [ ] Environment variables set
- [ ] Default passwords changed
- [ ] SSL certificate auto-renewal configured
- [ ] Backup retention policy defined
- [ ] Disaster recovery plan documented

## Support

For issues or questions:
- Check logs: `sudo journalctl -u <service> -n 100`
- Check Nginx logs: `/var/log/nginx/error.log`
- Check backend logs: `/var/log/attendance-backend.log`
- Check Celery logs: `/var/log/celery-worker.log`