# AI-Brain Docker & Infrastructure Audit Report

วันที่ตรวจสอบ: 10 สิงหาคม 2026  
ขอบเขต: Docker services, network connections, SSH access, n8n, PostgreSQL, OCR, Garmin, Private API และ Cloudflare Tunnel

## 1. Server Inventory

### AI-Brain

| รายการ | ค่า |
|---|---|
| Hostname | `ai-brain` |
| Tailscale IP | `100.68.88.63` |
| SSH user | `kanfullbuster` |
| SSH command | `ssh kanfullbuster@100.68.88.63` |
| Project path | `/home/kanfullbuster/n8n-zort` |
| Main public service | n8n ผ่าน Cloudflare Tunnel |
| Docker Compose file | `/home/kanfullbuster/n8n-zort/docker-compose.yml` |

ห้ามเก็บ password, API key หรือ tunnel token ไว้ในรายงานนี้ ให้ใช้ `.env` หรือ secret management เท่านั้น

### MDS

| รายการ | ค่า |
|---|---|
| Hostname | `mds` |
| Tailscale IP | `100.75.200.54` |
| SSH user | `mds` |
| SSH command | `ssh mds@100.75.200.54` |
| Scope | ระบบ n8n/บริการของ MDS แยกจาก AI-Brain |

รายงานนี้โฟกัส `ai-brain` เป็นหลัก ไม่ได้ตรวจรายละเอียด Docker ของ MDS ในรอบนี้

## 2. AI-Brain Docker Services

### Core n8n stack

| Container | Image/หน้าที่ | Port | Health | Storage/การเชื่อมต่อ |
|---|---|---:|---|---|
| `n8n_zort` | n8n workflow engine | `5678` | healthy | เชื่อม `n8n_zort_postgres`, OCR, Garmin และ Private API |
| `n8n_zort_postgres` | PostgreSQL ของ n8n/ZORT | `5432` | healthy | เก็บ workflow, execution และข้อมูล ZORT/Private ที่ต่อไว้กับ DB นี้ |
| `n8n_zort_cloudflared` | Cloudflare Tunnel | - | running | route public hostname ไปยัง `n8n_zort:5678` |
| `adminer` | Web UI จัดการ PostgreSQL | `8080` | no healthcheck | ใช้เชื่อมต่อ PostgreSQL ตาม credentials ของแต่ละ database |

### Private services

| Container | หน้าที่ | Port | Health | การเชื่อมต่อ |
|---|---|---:|---|---|
| `private_api` | API ข้อมูลส่วนตัวและ file service | `3000` ภายใน | healthy | เชื่อม `private_postgres` ผ่าน `DATABASE_URL` |
| `private_postgres` | PostgreSQL แยกสำหรับ Private API | `5432` ภายใน | no healthcheck | ไม่ควรปนกับฐานข้อมูล n8n |

### Workout/OCR/integration services

| Container | หน้าที่ | Port | Health | การเชื่อมต่อ |
|---|---|---:|---|---|
| `paddle_ocr` | PaddleOCR ภาษาไทย | `8010` ภายใน | healthy | n8n เรียกผ่าน `PADDLE_OCR_URL` |
| `garmin_api` | ดึงและแปลงข้อมูล Garmin | `8000` ภายใน | healthy | n8n เรียก API เพื่อสร้าง workout logs |
| `player_api` | API รับงาน Player | `9733` ภายใน | healthy | เชื่อม `player_postgres` |
| `player_postgres` | PostgreSQL ของ Player | `5432` ภายใน | healthy | ใช้โดย `player_api` |

### Other services on the same host

| Container | หน้าที่ | Network/สถานะ |
|---|---|---|
| `sailfish_collector` | Sailfish collector | แยก network, unhealthy |
| `sailfish_archive_postgres` | DB archive ของ Sailfish | แยก network, running |
| `mcmod-mcp-server` | Minecraft MCP server | แยก network, healthy |
| `minecraft-console` | Minecraft console | running |
| `audioreader-next` | Audio Reader web app | อยู่ใน n8n network, running |
| `notebooklm-mcp` | NotebookLM MCP service | แยก network, healthy |
| `notebooklm-tunnel` | Cloudflare Tunnel ของ NotebookLM | running |

## 3. Connection Map

```text
Internet / Telegram / external clients
                |
                v
       Cloudflare Tunnel
                |
                v
          n8n_zort:5678
                |
   +------------+-------------+----------------+
   |                          |                |
   v                          v                v
n8n_zort_postgres       paddle_ocr:8010    garmin_api:8000
   |                          |                |
   |                          +----------------+
   |
   +--> Private workflows --> private_api:3000 --> private_postgres
   |
   +--> Player workflows --> player_api:9733 --> player_postgres
   |
   +--> ZORT ETL/reporting

adminer:8080 --> manually connects to PostgreSQL databases
```

## 4. n8n Data Flow

### Telegram Private

```text
Telegram Trigger
      |
      v
Detect Telegram Action
      |
      v
Command log / audit
      |
      v
Switch / route action
      |
      +--> Food: eat, caleat, trackeat
      +--> OCR: image/slip -> PaddleOCR -> receipt_logs
      +--> Workout: Garmin, routine, workout, progress, week
      +--> Budget: budget cycle, receipts, expense summary
      +--> Utility: help, debug, today
      +--> Telegram reply / error fallback
```

### OCR slip flow

```text
Telegram image
      |
      v
PaddleOCR v5-th
      |
      v
Parse bank, amount, reference number
      |
      v
receipt_logs in PostgreSQL
      |
      +--> duplicate reference detection
      +--> budget cycle assignment
      +--> /slips and /budget detail
      +--> Telegram confirmation
```

### Workout flow

```text
Garmin URL
      |
      v
garmin_api
      |
      v
Workout/activity tables
      |
      +--> /workout
      +--> /routine
      +--> /progress
      +--> /week -> AI analysis
```

### ZORT flow

```text
ZORT API
      |
      v
n8n ETL workflow
      |
      v
n8n_zort_postgres
      |
      +--> daily report
      +--> sales/inventory queries
      +--> downstream API/dashboard work
```

## 5. Important Environment Variables

ตรวจพบว่าระบบมี environment หลักสำหรับ:

- n8n database connection และ encryption key
- n8n public URL / secure cookie / proxy hops
- ZORT API base URL, API key และ secret
- `PADDLE_OCR_URL`
- Garmin credentials และ token store
- Private API token, signing key และ encryption key
- Player API database/token settings
- Telegram owner/user guard
- PostgreSQL credentials
- Cloudflare tunnel credential

ค่าจริงทั้งหมดถูกปกปิดในการตรวจสอบและไม่ควรใส่ลงใน Git repository

## 6. Current Health Findings

### Healthy

- n8n
- n8n PostgreSQL
- PaddleOCR
- Garmin API
- Private API
- Player API
- Player PostgreSQL
- MCP server servicesที่มี healthcheck

### Needs attention

1. `sailfish_collector` อยู่สถานะ `unhealthy` และเป็นระบบแยกจาก Private/n8n
2. `private_postgres` ยังไม่มี healthcheck
3. `adminer` ไม่มี healthcheck
4. PostgreSQL หลักมีการ publish port `5432` ออกทุก interface ควรจำกัดให้เข้าผ่าน Docker network หรือ Tailscale
5. Adminer publish port `8080` ออกทุก interface ควรป้องกันด้วย VPN, Tailscale หรือ Cloudflare Access
6. Cloudflare Tunnel token อยู่ใน runtime command ของ container ควรย้ายไปใช้ credential file/secret และควร rotate หากเคยถูกเปิดเผย
7. มีหลาย PostgreSQL instance ต้องกำหนดชื่อ database ให้ชัดเจนเพื่อป้องกันการเขียนผิดฐาน
8. Container ที่ไม่มี healthcheck ยังอาจแสดง `running` ทั้งที่แอปภายในมีปัญหา

## 7. Recommended Security Rules

- ไม่เปิด PostgreSQL สู่ public network
- จำกัด Adminer ให้เข้าผ่าน Tailscale หรือ localhost
- ใช้ Docker secrets หรือไฟล์ `.env` ที่ไม่ commit เข้า Git
- แยก credentials ของ n8n, Private, Player และ Sailfish
- เพิ่ม healthcheck ให้ `private_postgres`, `adminer` และบริการที่ยังไม่มี healthcheck
- สำรอง PostgreSQL แยกตาม database
- ตั้ง log retention และไม่เก็บข้อมูลส่วนตัวเกินความจำเป็น
- ใช้ Telegram owner guard กับคำสั่งข้อมูลส่วนบุคคลและรายงานการเงิน

## 8. Useful Read-only Commands

```bash
cd /home/kanfullbuster/n8n-zort
docker compose ps
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker inspect --format '{{.Name}} {{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' $(docker ps -q)
```

ตรวจ environment โดยไม่แสดงค่า secret:

```bash
docker inspect <container> \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | sed -E 's/=.*$/=<set>/'
```

## 9. Scope Boundary

ระบบที่เกี่ยวกับ n8n/Private บน `ai-brain` ใช้ชุดหลักดังนี้:

```text
n8n_zort
n8n_zort_postgres
n8n_zort_cloudflared
paddle_ocr
garmin_api
private_api
private_postgres
player_api
player_postgres
adminer
```

ส่วน Sailfish, Minecraft, Audio Reader และ NotebookLM เป็นบริการอื่นบน host เดียวกัน ไม่ควรแก้ไขขณะปรับปรุง Private/n8n หากไม่ได้ตรวจ dependency เพิ่มเติม
