#!/usr/bin/env python3
"""
Generate the Smart AI Attendance System -- User Manual PDF.
Run:  pip install fpdf2 && python generate_user_manual_pdf.py
Output: docs/user_manual.pdf
"""

import os
from fpdf import FPDF

os.makedirs("docs", exist_ok=True)

BRAND   = (29, 158, 117)
DARK    = (30, 30, 30)
GRAY    = (90, 90, 90)
LGRAY   = (180, 180, 180)
WHITE   = (255, 255, 255)
ACCENT  = (41, 128, 185)
WARN    = (192, 57, 43)
TABLE_H = (44, 62, 80)


class Manual(FPDF):
    def header(self):
        if self.page_no() <= 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 8, "Smart AI Attendance System -- User Manual", align="C")
        self.set_draw_color(*LGRAY)
        self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
        self.ln(6)
        self.set_text_color(*DARK)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GRAY)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def cover(self, title, subtitle):
        self.set_fill_color(*TABLE_H)
        self.rect(0, 0, self.w, self.h, "F")
        self.set_y(60)
        self.set_font("Helvetica", "B", 36)
        self.set_text_color(*WHITE)
        self.cell(0, 14, title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 16)
        self.set_text_color(*BRAND)
        self.cell(0, 10, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(20)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*LGRAY)
        self.cell(0, 8, "Complete Guide for End Users", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "Version 1.1  |  2026", align="C")

    def chapter(self, number, title):
        self.add_page()
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(*BRAND)
        self.cell(0, 12, f"{number}.  {title}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*BRAND)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_line_width(0.2)
        self.ln(6)
        self.set_text_color(*DARK)

    def section(self, title):
        self._reset_x()
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*ACCENT)
        self.ln(4)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*DARK)
        self.ln(1)

    def _reset_x(self):
        self.set_x(self.l_margin)

    def body(self, text):
        self._reset_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text, level=0):
        self._reset_x()
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        prefix = ("   " * (level + 1)) + "- "
        self.multi_cell(0, 5.5, prefix + text)

    def note(self, text, color=None):
        c = color or ACCENT
        self.set_fill_color(235, 245, 255)
        self.set_draw_color(*c)
        self._reset_x()
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*c)
        self.multi_cell(self.w - self.l_margin - self.r_margin, 5, text, border="L", fill=True)
        self.set_text_color(*DARK)
        self._reset_x()
        self.ln(2)

    def table_header(self, cols):
        self.set_fill_color(*TABLE_H)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        for label, width in cols:
            self.cell(width, 7, label, border=1, fill=True)
        self.ln()
        self.set_text_color(*DARK)

    def table_row(self, cells, widths, shade=False):
        if shade:
            self.set_fill_color(245, 245, 245)
        self.set_font("Helvetica", "", 9)
        for text, w in zip(cells, widths):
            self.cell(w, 6, str(text), border=1, fill=shade)
        self.ln()

    def step(self, number, text):
        self.set_fill_color(*BRAND)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(8, 7, str(number), fill=True, align="C")
        self.set_fill_color(245, 250, 248)
        self.set_text_color(*DARK)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 7, "  " + text, border="B", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)


# ── Build PDF ─────────────────────────────────────────────────────────────────
pdf = Manual()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(20, 20, 20)

# Cover
pdf.add_page()
pdf.cover("Smart AI Attendance", "User Manual")

# ── Chapter 1: Introduction ───────────────────────────────────────────────────
pdf.chapter(1, "Introduction")
pdf.body(
    "Smart AI Attendance is an automated attendance tracking system powered by facial recognition. "
    "It uses AI cameras to detect and identify employees in real time, automatically recording "
    "check-ins and check-outs without any manual action from staff."
)
pdf.section("What the system does")
for item in [
    "Recognises employees from camera feeds using ArcFace AI (512-dimensional face embeddings)",
    "Records check-in and check-out times automatically",
    "Calculates late arrivals, early departures, and overtime based on configured shift times",
    "Sends security alerts for intruders, blacklisted persons, loitering, and spoof attempts",
    "Shows real-time occupancy counts per zone and building-wide",
    "Generates monthly attendance reports as downloadable CSV files",
]:
    pdf.bullet(item)
pdf.ln(3)

pdf.section("Who uses it")
cols = [("Role", 35), ("Level", 25), ("What they can do", 130)]
pdf.table_header(cols)
rows = [
    ("super_admin", "6", "Full system access"),
    ("admin", "5", "All tenant features: cameras, users, bulk operations, alert config"),
    ("hr", "4", "Add/edit/deactivate employees, enroll faces, manual attendance overrides"),
    ("manager", "3", "Read-only dashboard + face match"),
    ("security", "2", "Read-only + acknowledge security alerts"),
    ("viewer", "1", "Read-only dashboard"),
]
for i, row in enumerate(rows):
    pdf.table_row(row, [35, 25, 130], shade=(i % 2 == 0))
pdf.ln(3)
pdf.note("Every user can change their own password from the sidebar regardless of role.")

# ── Chapter 2: Getting Started ────────────────────────────────────────────────
pdf.chapter(2, "Getting Started")
pdf.section("Accessing the dashboard")
pdf.body("Open a web browser and go to your organisation's dashboard URL (e.g. http://192.168.1.10 or https://attendance.yourcompany.com).")

pdf.section("Logging in")
pdf.step(1, "Enter your email address")
pdf.step(2, "Enter your password")
pdf.step(3, "Click Sign In")
pdf.ln(3)
pdf.note("Default admin credentials on first install: admin@demo.com / admin123 -- change these immediately.", color=WARN)

pdf.section("Changing your password (first login)")
pdf.body("After logging in, change the default password immediately:")
pdf.step(1, "Find the sidebar on the left side of the screen")
pdf.step(2, "Click 'Change Password' near the bottom of the sidebar")
pdf.step(3, "Enter your current password (admin123 on first login)")
pdf.step(4, "Enter and confirm your new password (minimum 8 characters)")
pdf.step(5, "Click 'Change Password'")
pdf.ln(3)
pdf.note("Passwords are always stored as bcrypt hashes -- the system never stores your plain-text password.")

pdf.section("Understanding the sidebar")
pdf.body("The sidebar is visible on every page. It contains:")
for item in [
    "Your role badge (coloured chip showing your current role)",
    "Navigation links to all pages (active page is highlighted in blue)",
    "Change Password button",
    "Theme toggle (switch between light and dark mode)",
    "Sign Out button",
]:
    pdf.bullet(item)

# ── Chapter 3: Dashboard Overview ────────────────────────────────────────────
pdf.chapter(3, "Dashboard Overview")
pdf.body(
    "The Overview page is the first thing you see after logging in. It gives you a complete "
    "snapshot of today's attendance at a glance."
)

pdf.section("Stat cards (top row)")
cols = [("Card", 50), ("What it shows", 140)]
pdf.table_header(cols)
stat_rows = [
    ("Present today", "Number of employees who have checked in today"),
    ("Absent", "Total employees minus those present"),
    ("Late arrivals", "Employees who checked in after their grace period"),
    ("Visitors today", "Unknown persons detected by cameras today"),
    ("Attendance %", "Present / total employees × 100"),
]
for i, r in enumerate(stat_rows):
    pdf.table_row(r, [50, 140], shade=(i % 2 == 0))
pdf.ln(3)

pdf.section("Live Cameras panel")
pdf.body(
    "Below the stat cards, the Live Cameras panel shows a grid of real-time MJPEG streams "
    "from all registered cameras. Each tile shows:"
)
for item in [
    "The live video feed with AI bounding boxes drawn around detected persons",
    "A green 'Live' dot if the edge node is connected, grey 'Offline' if not",
    "A direction badge (Entrance / Exit / Interior) in the top-left corner",
    "Camera name and location below the video",
]:
    pdf.bullet(item)
pdf.note("Camera streams require the edge node to be running. Without it, tiles show 'Edge node offline'.")

pdf.section("Charts")
pdf.body("Two charts appear side-by-side below the camera panel:")
pdf.bullet("Occupancy Cards (left): current headcount in the building and per zone, refreshed every 10 seconds")
pdf.bullet("Weekly Attendance Rate (right): bar chart of attendance % for each day of the past 7 days")
pdf.ln(2)
pdf.body("Below these, the Hourly Entry/Exit chart shows entry and exit counts per hour for today.")

pdf.section("Recent check-ins table")
pdf.body(
    "The three-column section at the bottom shows recent activity in real time:"
)
pdf.bullet("Recent check-ins (left): table of today's attendance logs with employee name, check-in/out times, overtime, and status")
pdf.bullet("Live feed (centre): real-time stream of recognition events as they happen")
pdf.bullet("Security alerts (right): the 6 most recent security alerts")
pdf.ln(2)
pdf.note("HR users and above can click the pencil icon to edit a log or the trash icon to delete it. Reset Today (admin only) clears all logs for the current date.")

# ── Chapter 4: Employee Management ───────────────────────────────────────────
pdf.chapter(4, "Employee Management")
pdf.body("The Employees page lists all active employees. HR users and above can add, edit, and manage employees.")

pdf.section("Adding an employee")
pdf.step(1, "Click 'Add Employee' (top-right, visible to HR+ roles)")
pdf.step(2, "Fill in Full Name (required), Employee Code, Department, Designation, Email, Mobile Number")
pdf.step(3, "The Department and Designation fields offer autocomplete suggestions -- start typing to see options")
pdf.step(4, "Click 'Add Employee' to save")
pdf.ln(3)
pdf.note("Phone numbers should be in Bangladesh format: +880 1XXX-XXXXXX")

pdf.section("Enrolling a face")
pdf.body(
    "Face enrollment links a photo to an employee so the AI can recognise them. "
    "Without enrollment, the system cannot identify the person on camera."
)
pdf.step(1, "Find the employee in the list")
pdf.step(2, "Click the camera icon in the Actions column")
pdf.step(3, "Drag and drop or click to browse for photos (up to 10 images)")
pdf.step(4, "Use clear, front-facing photos in good lighting. Variety helps accuracy (different angles, lighting)")
pdf.step(5, "Click 'Enroll Photos' -- each photo is processed and a result shown (OK or Failed)")
pdf.ln(2)
pdf.note("After enrollment, the edge node will sync the new face data within 60 seconds automatically.")

pdf.section("Employee flags")
pdf.body("The Actions column has two toggle buttons visible to admin users:")
pdf.bullet("Blacklist (triangle icon): marks an employee as blacklisted -- every detection triggers a high-severity alert")
pdf.bullet("VIP (star icon): marks an employee as VIP -- detections trigger a VIP alert and Slack notification")
pdf.ln(2)

pdf.section("Deactivating an employee")
pdf.body("Click the trash icon to deactivate an employee. They will no longer appear in active reports but their historical data is preserved.")

# ── Chapter 5: Shift Management ──────────────────────────────────────────────
pdf.chapter(5, "Shift Management")
pdf.body(
    "Shifts tell the system what your working hours are. Without a shift assigned, the system "
    "cannot calculate whether someone is late or left early. Go to Shifts in the sidebar."
)

pdf.section("How shifts affect attendance")
cols = [("Event", 55), ("Condition", 75), ("Result", 60)]
pdf.table_header(cols)
shift_rows = [
    ("Check-in", "After Start + Grace period", "Marked Late"),
    ("Check-in", "Before Start + Grace period", "On time"),
    ("Check-out", "Before End - Early buffer", "Early Leave"),
    ("Check-out", "After End time", "Overtime recorded"),
]
for i, r in enumerate(shift_rows):
    pdf.table_row(r, [55, 75, 60], shade=(i % 2 == 0))
pdf.ln(3)
pdf.body("Example: Shift 09:00-18:00, grace 10 min, early buffer 15 min")
pdf.bullet("Late if check-in after 09:10")
pdf.bullet("Early leave if check-out before 17:45")
pdf.bullet("Overtime for every second after 18:00")

pdf.section("Creating a shift")
pdf.step(1, "Click 'New Shift'")
pdf.step(2, "Enter a name (e.g. Morning Shift, Night Shift)")
pdf.step(3, "Set Start Time and End Time using the time pickers")
pdf.step(4, "Set Grace Period (minutes after start before 'late' is recorded)")
pdf.step(5, "Set Early Leave Buffer (minutes before end where leaving is still OK)")
pdf.step(6, "Select work days by clicking the day buttons (blue = selected)")
pdf.step(7, "Review the live summary showing exact thresholds, then click Create Shift")

pdf.section("Assigning a shift to an employee")
pdf.step(1, "Click 'Assign Employee'")
pdf.step(2, "Select the employee from the dropdown")
pdf.step(3, "Select the shift")
pdf.step(4, "Set the Effective From date (when the assignment starts)")
pdf.step(5, "Click Assign")
pdf.ln(2)
pdf.note("A new assignment automatically closes the previous one. Each employee has one active shift at a time.")

# ── Chapter 6: Camera Management ─────────────────────────────────────────────
pdf.chapter(6, "Camera Management")
pdf.body("Cameras page shows all registered cameras with their live streams. Admin users can add, edit, and remove cameras.")

pdf.section("Adding a camera")
pdf.step(1, "Click '+ Add camera' (admin only)")
pdf.step(2, "Enter Name and Location")
pdf.step(3, "Enter the RTSP/HTTP stream URL (e.g. rtsp://user:pass@192.168.1.10:554/stream)")
pdf.step(4, "Select Direction: Entrance (check-in), Exit (check-out), or Interior")
pdf.step(5, "Select Role: General, Meeting Room, Reception, or Entrance Gate")
pdf.step(6, "Set Target FPS (lower = less CPU, 5-10 recommended)")
pdf.step(7, "Tick 'Restricted area' if any detection in this area should trigger an alert")
pdf.step(8, "Click Save")

pdf.section("Camera stream URLs")
cols = [("Camera type", 55), ("URL format", 135)]
pdf.table_header(cols)
cam_rows = [
    ("IP camera (RTSP)", "rtsp://username:password@192.168.1.10:554/stream"),
    ("HTTP webcam (Android)", "http://192.168.1.10:8080/video"),
    ("USB webcam (Linux)", "0 or 1 (device index)"),
    ("USB webcam (Windows)", "Use edge_standalone.py script"),
]
for i, r in enumerate(cam_rows):
    pdf.table_row(r, [55, 135], shade=(i % 2 == 0))

# ── Chapter 7: Security Alerts ───────────────────────────────────────────────
pdf.chapter(7, "Security Alerts")
pdf.body(
    "The system fires security alerts automatically when specific conditions are detected. "
    "Go to Alerts or Security Alerts in the sidebar to view them."
)

pdf.section("Alert types")
cols = [("Type", 40), ("Severity", 25), ("Triggered when", 125)]
pdf.table_header(cols)
alert_rows = [
    ("Intruder", "High", "Unknown person detected outside business hours"),
    ("Blacklist", "High", "A blacklisted employee is detected on camera"),
    ("Spoof attempt", "High", "Camera detects a photo or screen (not a real face)"),
    ("Restricted area", "High", "Any detection in a camera marked as restricted"),
    ("After-hours", "Medium", "Employee detected outside their shift window"),
    ("Loitering", "Medium", "Employee near same camera for longer than threshold"),
    ("VIP", "Low", "VIP-flagged employee detected"),
    ("Unknown person", "Low", "Face detected but does not match any enrolled employee"),
]
for i, r in enumerate(alert_rows):
    pdf.table_row(r, [40, 25, 125], shade=(i % 2 == 0))
pdf.ln(3)

pdf.section("Acknowledging alerts")
pdf.body(
    "Security users and above can acknowledge alerts to mark them as reviewed. "
    "Click the 'Ack' button on any unacknowledged alert. "
    "The Alerts page has a filter toggle: Unacknowledged (default) or All."
)

pdf.section("Alert configuration")
pdf.body("Admins can adjust alert thresholds via the API or by editing the config. Key thresholds:")
pdf.bullet("Confidence threshold: minimum face match score to identify a person (default 0.82)")
pdf.bullet("Liveness threshold: minimum anti-spoof score to treat a face as live (default 0.80)")
pdf.bullet("Cooldown minutes: minimum gap between events for the same person per camera (default 5)")
pdf.bullet("Loitering threshold: minutes near one camera before loitering alert fires (default 10)")

# ── Chapter 8: Analytics ─────────────────────────────────────────────────────
pdf.chapter(8, "Analytics")
pdf.body("The Analytics page shows aggregated data about occupancy and shift compliance.")

pdf.section("Building occupancy")
pdf.body("Shows how many people are currently inside the building. Updated every 10 seconds via Redis counters. Separate zone counters appear below (e.g. Reception: 3, Floor 2: 12).")

pdf.section("Department occupancy")
pdf.body("Grid of cards showing current headcount per department. Useful for fire evacuation and floor capacity management.")

pdf.section("Shift compliance table")
pdf.body("Shows this week's on-time percentage per employee:")
pdf.bullet("On-time: check-in before the late threshold")
pdf.bullet("Late: check-in after the late threshold")
pdf.bullet("On-time %: (on-time days / total working days) x 100")
pdf.ln(2)
pdf.note("Colour codes: green >= 90%, amber >= 70%, red < 70%")

# ── Chapter 9: Reports ────────────────────────────────────────────────────────
pdf.chapter(9, "Reports")
pdf.body("The Reports page lets you export attendance data for payroll, HR records, and compliance.")

pdf.section("Monthly CSV export")
pdf.step(1, "Select the year from the first dropdown")
pdf.step(2, "Select the month from the second dropdown")
pdf.step(3, "Click 'Download CSV'")
pdf.step(4, "The browser downloads a CSV file named attendance_YYYY_MM.csv")
pdf.ln(2)
pdf.body("The CSV contains one row per employee per day with: employee name, code, department, date, check-in time, check-out time, status, late flag, early-leave flag, overtime seconds, and working hours.")

pdf.section("Shift compliance report")
pdf.body("Below the CSV export, the page shows the same shift compliance table as the Analytics page but for the current week.")

# ── Chapter 10: Admin Panel ────────────────────────────────────────────────────
pdf.chapter(10, "Admin Panel")
pdf.body("The Admin panel (sidebar 'Admin' link, visible to admin+ roles) lets you manage all user accounts in the system.")

pdf.section("Adding a new user")
pdf.step(1, "Click 'Add User'")
pdf.step(2, "Enter full name, email address, and a password (minimum 8 characters)")
pdf.step(3, "Select a role from the dropdown")
pdf.step(4, "Click 'Create User'")

pdf.section("Changing a user's role")
pdf.step(1, "Find the user in the table")
pdf.step(2, "Click the pencil (edit) icon")
pdf.step(3, "Change the role from the dropdown")
pdf.step(4, "Optionally toggle the Active switch")
pdf.step(5, "Click 'Save Changes'")
pdf.ln(2)
pdf.note("You cannot change your own role. Changes take effect on the user's next login (or next token refresh).")

pdf.section("Deactivating a user")
pdf.body("Click the user-minus icon on any active user to deactivate their account. They will be logged out on their next API call and cannot log in again until reactivated.")

# ── Chapter 11: Troubleshooting ───────────────────────────────────────────────
pdf.chapter(11, "Troubleshooting")

pdf.section("Cannot log in")
pdf.bullet("Check your email address -- it is case-insensitive but must match exactly")
pdf.bullet("If you see 'Too many attempts' -- wait 1 minute and try again (rate limiting)")
pdf.bullet("Contact your admin to reset your password if forgotten")

pdf.section("Face not recognised on camera")
pdf.bullet("Check the employee is enrolled (green 'Enrolled' badge in the Employees table)")
pdf.bullet("Upload better photos: well-lit, front-facing, no sunglasses")
pdf.bullet("The edge node resyncs faces every 60 seconds -- wait a moment after enrolling")
pdf.bullet("Check the Confidence Threshold setting -- lowering it makes recognition more lenient")

pdf.section("Camera shows 'Edge node offline'")
pdf.bullet("The edge node (AI camera processor) is not running or is not connected to the network")
pdf.bullet("Contact your system administrator to check the edge node status")
pdf.bullet("Attendance logging still works if cameras are registered and the edge node comes back online")

pdf.section("Attendance log is missing or wrong")
pdf.bullet("HR users can manually edit a log: click the pencil icon on the Overview page")
pdf.bullet("If a camera is set as 'exit' direction, check-outs are recorded. If only 'entrance' cameras exist, only check-ins are recorded")

pdf.section("I see no alerts even though someone should trigger one")
pdf.bullet("Check the employee is enrolled (unknown people do not trigger blacklist/VIP alerts)")
pdf.bullet("Check the cooldown setting -- the same person cannot trigger the same alert more than once per cooldown period")
pdf.bullet("Check the alert threshold settings in the admin config")

# ── Chapter 12: Glossary ──────────────────────────────────────────────────────
pdf.chapter(12, "Glossary")
cols = [("Term", 50), ("Definition", 140)]
pdf.table_header(cols)
glossary = [
    ("ArcFace", "AI model that converts a face photo into a 512-number embedding used for matching"),
    ("FAISS", "Fast AI similarity search library used to find the closest face embedding"),
    ("Edge node", "The device/service that processes camera frames and runs the AI pipeline"),
    ("RTSP", "Real Time Streaming Protocol -- standard protocol used by IP cameras"),
    ("MJPEG", "Motion JPEG -- streaming format used for the live camera preview"),
    ("Tenant", "An organisation using the system. All data is isolated per tenant"),
    ("Embedding", "A 512-dimensional numerical representation of a face"),
    ("Liveness", "Anti-spoof score -- distinguishes a real face from a photo or screen"),
    ("ByteTrack", "Tracking algorithm that assigns consistent IDs to moving persons across frames"),
    ("Cooldown", "Minimum time between two recognition events for the same person per camera"),
    ("Grace period", "Extra minutes after shift start before a check-in is counted as late"),
    ("EDGE_TOKEN", "Shared secret between backend and edge node for event authentication"),
    ("JWT", "JSON Web Token -- signed token used to authenticate API requests"),
    ("bcrypt", "Password hashing algorithm -- slow by design to resist brute-force attacks"),
    ("pgvector", "PostgreSQL extension that stores and searches vector embeddings"),
]
for i, r in enumerate(glossary):
    pdf.table_row(r, [50, 140], shade=(i % 2 == 0))

# Save
out = "docs/user_manual.pdf"
pdf.output(out)
print(f"User manual saved: {out}  ({os.path.getsize(out) // 1024} KB)")
