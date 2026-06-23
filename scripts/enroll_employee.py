import os
import httpx

BACKEND_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@demo.com"
ADMIN_PASSWORD = "admin123"
EMPLOYEE_CODE = "DEMO-001"
EMPLOYEE_NAME = "Rabiul Hasnat"
IMAGE_DIR = r"C:\Users\Strang3\Desktop\New folder"

def get_token():
    print("Logging into backend...")
    r = httpx.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    data = r.json()
    print("Authentication successful.")
    return data["access_token"]

def get_or_create_employee(token):
    headers = {"Authorization": f"Bearer {token}"}
    
    # Check if employee exists
    print("Listing employees to find if they are already created...")
    r = httpx.get(f"{BACKEND_URL}/api/v1/employees?include_inactive=true", headers=headers)
    r.raise_for_status()
    employees = r.json()
    
    for emp in employees:
        if emp["employee_code"] == EMPLOYEE_CODE:
            print(f"Employee {EMPLOYEE_NAME} already exists with ID: {emp['id']}")
            return emp["id"]
            
    # Create employee
    payload = {
        "full_name": EMPLOYEE_NAME,
        "employee_code": EMPLOYEE_CODE,
        "email": "rabiul@demo.com",
        "department": "Engineering",
        "designation": "Software Engineer"
    }
    print("Creating new employee...")
    r = httpx.post(f"{BACKEND_URL}/api/v1/employees", json=payload, headers=headers)
    r.raise_for_status()
    emp = r.json()
    print(f"Created employee with ID: {emp['id']}")
    return emp["id"]

def clear_existing_face_data(token, emp_id):
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Clearing existing face data for employee {emp_id}...")
    try:
        r = httpx.delete(f"{BACKEND_URL}/api/v1/enrollment/{emp_id}", headers=headers)
        if r.status_code == 200:
            print("Successfully cleared face data.")
        else:
            print(f"Response: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Could not clear face data (might not exist): {e}")

def enroll_images(token, emp_id):
    headers = {"Authorization": f"Bearer {token}"}
    files = sorted(os.listdir(IMAGE_DIR))
    images = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    
    if not images:
        print("No images found to enroll!")
        return
        
    print(f"Found {len(images)} images to enroll. Starting upload...")
    for idx, img_name in enumerate(images):
        img_path = os.path.join(IMAGE_DIR, img_name)
        print(f"Uploading image {idx+1}/{len(images)}: {img_name}")
        with open(img_path, "rb") as f:
            file_payload = {"file": (img_name, f.read(), "image/jpeg")}
            
        r = httpx.post(
            f"{BACKEND_URL}/api/v1/employees/{emp_id}/enroll",
            files=file_payload,
            headers=headers,
            timeout=30.0
        )
        if r.status_code == 200:
            print(f"Successfully enrolled image {img_name}. Current version: {r.json().get('version')}")
        else:
            print(f"Failed to enroll image {img_name}: {r.status_code} - {r.text}")

def main():
    try:
        token = get_token()
        emp_id = get_or_create_employee(token)
        clear_existing_face_data(token, emp_id)
        enroll_images(token, emp_id)
        print("Enrollment script finished.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
