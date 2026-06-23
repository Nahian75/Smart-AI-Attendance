# API Reference (v1)

Base URL: `/api/v1`  
Auth: `Authorization: Bearer <JWT>` (obtain from `POST /auth/login`)

---

## Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | — | Exchange email + password for JWT |
| POST | `/auth/refresh` | bearer | Refresh JWT |

**Login request:**
```json
{ "email": "admin@demo.com", "password": "admin123" }
```
**Login response:**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

---

## Employees

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/employees` | viewer | List employees (active only by default) |
| POST | `/employees` | hr | Create employee |
| GET | `/employees/{id}` | viewer | Get single employee |
| PATCH | `/employees/{id}` | hr | Update employee fields (partial) |
| DELETE | `/employees/{id}` | admin | Deactivate employee |

**Query params for GET `/employees`:**

| Param | Default | Description |
|---|---|---|
| `include_inactive` | `false` | Set `true` to include deactivated employees |

**Employee object:**
```json
{
  "id": "uuid",
  "full_name": "Jane Smith",
  "employee_code": "EMP-001",
  "email": "jane@example.com",
  "phone": "+1234567890",
  "department": "Engineering",
  "designation": "Senior Engineer",
  "is_enrolled": true,
  "is_active": true,
  "is_blacklisted": false,
  "is_vip": false,
  "face_enrolled_at": "2024-01-15T10:30:00Z"
}
```

---

## Face Enrollment

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/employees/{id}/enroll` | hr | Upload a face photo and store embedding |
| GET | `/enrollment/export` | edge | Export all embeddings for FAISS sync |
| POST | `/enrollment/match` | manager | Match a probe embedding against the index |
| DELETE | `/enrollment/{id}` | hr | Delete all face embeddings (GDPR) |

### `POST /employees/{id}/enroll`

Upload a JPEG/PNG photo (`multipart/form-data`, field `file`). The backend:
1. Decodes the image
2. Runs InsightFace `buffalo_l` to detect faces and extract the 512-d ArcFace embedding
3. Stores the embedding in pgvector
4. Sets `is_enrolled = true` and `face_enrolled_at` on the employee

**Response:**
```json
{
  "employee_id": "uuid",
  "embedding_id": "uuid",
  "det_score": 0.94,
  "photo_angle": "front",
  "message": "Face enrolled successfully."
}
```

**Errors:**
- `400` — No face detected in the image (check lighting, face must be clearly visible)
- `404` — Employee not found

### `GET /enrollment/export`

Returns all enrolled embeddings for the authenticated tenant. Used by edge nodes to build their local FAISS index at startup.

```json
[
  {
    "employee_id": "uuid",
    "embedding": [0.012, -0.034, ...],  // 512 floats
    "photo_angle": "front"
  }
]
```

---

## Attendance

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/attendance/event` | edge | Ingest a recognition event from edge node |
| GET | `/attendance/logs` | viewer | Paginated attendance log |
| GET | `/attendance/summary?date=` | viewer | Daily headcount summary |
| GET | `/attendance/live` | viewer | Last 50 live events |

### `POST /attendance/event`

Sent by edge nodes when a face matches.

```json
{
  "camera_id": "cam-entrance",
  "employee_id": "uuid",
  "confidence": 0.87,
  "is_live": true,
  "spoof_score": 1.0,
  "direction": "entrance",
  "timestamp": 1720000000.0
}
```

### `GET /attendance/summary?date=YYYY-MM-DD`

```json
{
  "date": "2024-06-13",
  "total_employees": 24,
  "present": 19,
  "absent": 5,
  "late": 3,
  "attendance_rate": 79.2
}
```

---

## Cameras

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/cameras` | viewer | List configured cameras |
| POST | `/cameras` | admin | Register a camera |
| GET | `/cameras/{id}` | viewer | Get camera details |
| PUT | `/cameras/{id}` | admin | Update camera |
| DELETE | `/cameras/{id}` | admin | Remove camera |
| POST | `/cameras/{id}/heartbeat` | edge | Update camera last-seen timestamp |

**Camera object:**
```json
{
  "id": "uuid",
  "name": "Main Entrance",
  "location": "Building A",
  "rtsp_url": "rtsp://...",
  "fps_target": 10,
  "status": "online",
  "direction": "entrance",
  "camera_role": "entrance_gate",
  "camera_zone": "floor_1",
  "is_restricted": false,
  "last_seen_at": "2024-06-13T08:00:00Z"
}
```

---

## Reports

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/reports/monthly.csv?year=&month=` | viewer | Full month attendance as CSV |
| GET | `/reports/weekly` | viewer | 7-day attendance rate array |

**`GET /reports/weekly` response:**
```json
[
  { "date": "2024-06-07", "rate": 82 },
  { "date": "2024-06-08", "rate": 75 },
  ...
]
```

---

## WebSocket — live events

```
WS /api/v1/ws/attendance/{tenant_id}?token=<JWT>
```

Pushes JSON messages whenever an attendance event is processed:

```json
{
  "type": "attendance_event",
  "employee_id": "uuid",
  "employee_name": "Jane Smith",
  "direction": "entrance",
  "confidence": 0.87,
  "timestamp": "2024-06-13T08:05:00Z",
  "camera_id": "cam-entrance"
}
```

Also pushes `unknown_person` events when an unrecognised face is detected:
```json
{
  "type": "unknown_person",
  "camera_id": "cam-entrance",
  "timestamp": "2024-06-13T08:05:01Z"
}
```

---

## Roles

| Role | Permissions |
|---|---|
| `viewer` | Read logs, summaries, employee list, camera list |
| `hr` | + create/update employees, enroll/delete faces |
| `manager` | + run face match queries |
| `admin` | + manage cameras, deactivate employees |
| `edge` | attendance event ingest, camera heartbeat, enrollment export |
