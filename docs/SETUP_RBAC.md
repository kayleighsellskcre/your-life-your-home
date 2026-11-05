# 🔐 RBAC Setup Guide - Step by Step

## ✨ **What You're Getting:**

✅ **6 Professional Roles** (Owner, Admin, Support, Agent, Lender, Client)
✅ **30+ Permissions** (Fine-grained access control)
✅ **Audit Logging** (Track everything)
✅ **Impersonation** (Safe "View As" support mode)
✅ **MFA Ready** (TOTP for Owner/Admin)

---

## 🚀 **SETUP STEPS (15 minutes)**

### **Step 1: Reset Database & Create Your Admin Account**

```powershell
python scripts/reset_and_create_admin.py
```

**What it does:**
- Deletes ALL existing users (fresh start)
- Creates YOUR account as super admin
- Role: `owner` (full access)

**You'll need to provide:**
- Your full name
- Your email
- Your phone
- Password (8+ characters)

---

### **Step 2: Create RBAC Tables**

```powershell
python scripts/setup_rbac_tables.py
```

**Creates 7 new tables:**
- `roles` - Role definitions
- `permissions` - Permission definitions  
- `role_permissions` - Links roles to permissions
- `user_roles` - Links users to roles
- `audit_logs` - Security audit trail
- `impersonation_sessions` - Support mode tracking
- `mfa_settings` - MFA configuration

---

### **Step 3: Seed Roles & Permissions**

```powershell
python scripts/seed_roles_permissions.py
```

**Seeds:**
- 6 roles with descriptions
- 30+ permissions
- Role-permission mappings
- **Assigns YOU the Owner role automatically!**

---

### **Step 4: Install MFA Dependencies**

```powershell
pip install pyotp qrcode[pil]
```

---

### **Step 5: Restart Your App**

```powershell
python app.py
```

---

## ✅ **Verification**

After setup, verify it worked:

### **Check Your Roles:**

```powershell
python -c "
from database import get_connection
from rbac import get_user_roles, get_user_permissions

# Check user ID 1 (you)
roles = get_user_roles(1)
perms = get_user_permissions(1)

print('Your Roles:', [r['name'] for r in roles])
print('Your Permissions:', len(perms), 'permissions')
"
```

**Should show:**
```
Your Roles: ['owner']
Your Permissions: 30+ permissions
```

---

## 🎯 **What You Can Do Now:**

### **As Owner, you can:**

✅ **View ANY user's dashboard** (impersonation)
✅ **Manage roles** (assign/revoke)
✅ **View audit logs** (see all activity)
✅ **Manage MFA** (enable/disable for users)
✅ **Full access** to all features

### **Impersonation Example:**

```python
# In your admin dashboard, you'll have:
# "View As" button next to each user → Switch to their view
# Banner shows: "🔍 Support Mode: Viewing as [User Name]"
# "Exit Support Mode" button → Return to your admin view
```

---

## 📋 **Next Steps:**

After basic setup, I'll help you:

1. **Add MFA to your account** (Owner should have MFA!)
2. **Create admin dashboard** (manage users, view audits)
3. **Add impersonation UI** ("View As" buttons)
4. **Update login flow** (check MFA for Owner/Admin)

---

## 🐛 **Troubleshooting:**

### **"Module not found" errors:**
```powershell
pip install -r requirements.txt
```

### **"Table already exists" errors:**
- Safe to ignore - tables are `IF NOT EXISTS`

### **"Can't find admin account":**
```powershell
# Check if created:
python -c "from database import get_connection; c = get_connection(); print(c.execute('SELECT * FROM users').fetchall())"
```

---

## 🚀 **READY TO START?**

Run these commands IN ORDER:

```powershell
# 1. Reset & create admin
python scripts/reset_and_create_admin.py

# 2. Create RBAC tables  
python scripts/setup_rbac_tables.py

# 3. Seed data
python scripts/seed_roles_permissions.py

# 4. Install MFA
pip install pyotp qrcode[pil]

# 5. Restart app
python app.py
```

---

**Then tell me when done - I'll build the admin UI!** 🎉
