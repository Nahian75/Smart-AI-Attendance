#!/usr/bin/env bash
# ================================================================
#  Smart AI Attendance — Production Deployment
#
#  Usage:
#    ./deploy.sh                  auto-detect IP, auto-detect GPU
#    ./deploy.sh yourdomain.com   custom domain
#    ./deploy.sh --update         rebuild images, keep existing .env
#    ./deploy.sh --no-edge        skip edge node (dashboard only)
#    ./deploy.sh --gpu nvidia|amd|intel|cpu   force GPU type
# ================================================================
set -euo pipefail
cd "$(dirname "$0")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
step()  { echo -e "\n${BOLD}${CYAN}>> $*${NC}"; }

echo ""
echo -e "${BOLD}  ================================================"
echo   "   Smart AI Attendance — Production Deploy"
echo -e "  ================================================${NC}"
echo ""

# ── Parse args ────────────────────────────────────────────────────
UPDATE_ONLY=0; NO_EDGE=0; FORCE_GPU=""; SERVER_ARG=""
for arg in "$@"; do
    case "$arg" in
        --update)    UPDATE_ONLY=1 ;;
        --no-edge)   NO_EDGE=1 ;;
        --gpu=*)     FORCE_GPU="${arg#--gpu=}" ;;
        --gpu)       shift; FORCE_GPU="${1:-}" ;;
        *)           SERVER_ARG="$arg" ;;
    esac
done

# ── 1. Check dependencies ─────────────────────────────────────────
step "Checking dependencies"
command -v docker   > /dev/null 2>&1 || error "Docker not found. Install: https://docs.docker.com/get-docker/"
command -v openssl  > /dev/null 2>&1 || error "openssl required: apt install openssl"
command -v python3  > /dev/null 2>&1 || error "python3 required: apt install python3"
docker info         > /dev/null 2>&1 || error "Docker daemon not running: sudo systemctl start docker"
ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"

# ── 2. Detect GPU ─────────────────────────────────────────────────
step "Detecting GPU hardware"

GPU_TYPE="cpu"
GPU_OVERRIDE=""

if [ -n "$FORCE_GPU" ]; then
    GPU_TYPE="$FORCE_GPU"
    info "GPU type forced: $GPU_TYPE"
elif [ "$NO_EDGE" -eq 1 ]; then
    GPU_TYPE="none"
else
    # NVIDIA
    if command -v nvidia-smi > /dev/null 2>&1 && nvidia-smi > /dev/null 2>&1; then
        if docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 \
               nvidia-smi > /dev/null 2>&1; then
            GPU_TYPE="nvidia"
        else
            warn "nvidia-smi present but nvidia-container-toolkit not configured."
            warn "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            GPU_TYPE="cpu"
        fi

    # AMD ROCm
    elif command -v rocm-smi > /dev/null 2>&1 || [ -c /dev/kfd ]; then
        if [ -c /dev/kfd ] && [ -d /dev/dri ]; then
            GPU_TYPE="amd"
        else
            warn "AMD GPU detected but /dev/kfd or /dev/dri not accessible."
            warn "Add your user to the render group: sudo usermod -aG render,video $USER"
            GPU_TYPE="cpu"
        fi

    # Intel
    elif lspci 2>/dev/null | grep -qi "Intel.*Arc\|Intel.*Iris\|Intel.*UHD\|Intel.*HD Graphics"; then
        if [ -d /dev/dri ]; then
            GPU_TYPE="intel"
        else
            warn "Intel GPU detected but /dev/dri not accessible. Falling back to CPU."
            GPU_TYPE="cpu"
        fi
    fi
fi

case "$GPU_TYPE" in
    nvidia)
        GPU_OVERRIDE="-f docker-compose.prod.gpu.yml"
        ok "NVIDIA GPU — CUDA acceleration" ;;
    amd)
        GPU_OVERRIDE="-f docker-compose.prod.amd.yml"
        ok "AMD GPU — ROCm acceleration" ;;
    intel)
        GPU_OVERRIDE="-f docker-compose.prod.intel.yml"
        ok "Intel GPU — OpenVINO acceleration" ;;
    none)
        info "Edge node disabled (--no-edge)" ;;
    *)
        info "CPU only — no GPU acceleration" ;;
esac

COMPOSE_CMD="docker compose -f docker-compose.prod.yml ${GPU_OVERRIDE}"

# ── 3. Determine server URL ───────────────────────────────────────
step "Determining server address"

if [ -n "$SERVER_ARG" ]; then
    SERVER_HOST="${SERVER_ARG#http://}"; SERVER_HOST="${SERVER_HOST#https://}"; SERVER_HOST="${SERVER_HOST%/}"
else
    SERVER_HOST=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || \
                  curl -s --max-time 5 api.ipify.org 2>/dev/null || \
                  hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
fi

HTTP_URL="http://${SERVER_HOST}"
WS_URL="ws://${SERVER_HOST}"
info "Server address: ${HTTP_URL}"

# ── 4. Generate .env ──────────────────────────────────────────────
step "Configuring environment"

if [ -f ".env" ] && [ "$UPDATE_ONLY" -eq 1 ]; then
    info ".env exists — keeping existing secrets (--update mode)."
    if [ -n "$SERVER_ARG" ]; then
        sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${HTTP_URL}|" .env
        sed -i "s|^NEXT_PUBLIC_WS_URL=.*|NEXT_PUBLIC_WS_URL=${WS_URL}|" .env
        ok "Server URL updated to ${HTTP_URL}"
    fi
elif [ ! -f ".env" ]; then
    info "Generating secure secrets..."

    PG_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
    REDIS_PASS=$(openssl rand -base64 32 | tr -d '/+=' | head -c 24)
    SECRET_KEY=$(openssl rand -hex 32)
    EDGE_TOKEN=$(openssl rand -hex 32)
    FACE_KEY=$(python3 -c \
        "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

    cat > .env <<ENVFILE
# ── Database ─────────────────────────────────────────────────────
POSTGRES_USER=attendance
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=attendance_db

# ── Redis ────────────────────────────────────────────────────────
REDIS_PASSWORD=${REDIS_PASS}

# ── Backend ──────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
ENVIRONMENT=production
FACE_ENCRYPTION_KEY=${FACE_KEY}
CONFIDENCE_THRESHOLD=0.82
COOLDOWN_MINUTES=5
EVENT_RETENTION_DAYS=90

# ── Edge node ────────────────────────────────────────────────────
TENANT_ID=demo
EDGE_TOKEN=${EDGE_TOKEN}

# ── Frontend ─────────────────────────────────────────────────────
NEXT_PUBLIC_API_URL=${HTTP_URL}
NEXT_PUBLIC_WS_URL=${WS_URL}
NEXT_PUBLIC_EDGE_URL=
ENVFILE

    ok ".env created."
    echo ""
    echo -e "  ${YELLOW}${BOLD}SAVE THESE CREDENTIALS — shown only once:${NC}"
    echo    "  ─────────────────────────────────────────────────────"
    echo    "  POSTGRES_PASSWORD : ${PG_PASS}"
    echo    "  REDIS_PASSWORD    : ${REDIS_PASS}"
    echo    "  SECRET_KEY        : ${SECRET_KEY}"
    echo    "  EDGE_TOKEN        : ${EDGE_TOKEN}"
    echo    "  ─────────────────────────────────────────────────────"
    echo    "  Stored in .env — back up this file securely."
    echo ""
else
    info ".env already exists — keeping existing secrets."
fi

# ── 5. Build ──────────────────────────────────────────────────────
step "Building production images"
info "First build takes 10-20 min (downloading AI models). Subsequent builds use cache."
$COMPOSE_CMD build
ok "All images built."

# ── 6. Start ──────────────────────────────────────────────────────
step "Starting services"
$COMPOSE_CMD up -d
ok "Services started."

# ── 7. Wait for backend ───────────────────────────────────────────
step "Waiting for backend"
TRIES=0
until curl -s http://localhost:8000/health 2>/dev/null | grep -q '"ok"'; do
    TRIES=$((TRIES + 1))
    [ "$TRIES" -ge 90 ] && {
        warn "Backend slow to start. Check logs: docker compose -f docker-compose.prod.yml logs backend"
        break
    }
    printf "."
    sleep 3
done
echo ""
ok "Backend ready."

# ── 8. Seed ───────────────────────────────────────────────────────
step "Seeding database"
$COMPOSE_CMD exec -T backend python seed.py && ok "Database seeded." || \
    warn "Seed step had output above — check if this is expected."

# ── 9. Summary ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ================================================"
echo    "   Deployment complete"
echo -e "  ================================================${NC}"
echo    "   Dashboard   :  ${HTTP_URL}"
echo    "   Login       :  admin@demo.com / admin123"
echo    ""
echo -e "   ${YELLOW}Change the admin password immediately after${NC}"
echo    "   first login (sidebar > Change Password)."
echo    ""
echo    "   GPU         :  ${GPU_TYPE}"
echo    "   Logs        :  docker compose -f docker-compose.prod.yml logs -f"
echo    "   Stop        :  docker compose -f docker-compose.prod.yml down"
echo    "   Update      :  ./deploy.sh --update"
if [ "$HTTP_URL" != "http://localhost" ]; then
echo    ""
echo    "   Enable HTTPS (free SSL with Let's Encrypt):"
echo    "     sudo apt install certbot python3-certbot-nginx"
echo    "     sudo certbot --nginx -d ${SERVER_HOST}"
fi
echo    "  ================================================"
echo ""
