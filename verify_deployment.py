#!/usr/bin/env python3
"""
Railway Deployment Verification Script
Run this before deploying to catch common issues
"""

import os
import sys
from pathlib import Path

def check_file_exists(filename, required=True):
    """Check if a file exists"""
    exists = Path(filename).exists()
    status = "[OK]" if exists else ("[FAIL]" if required else "[WARN]")
    print(f"{status} {filename}: {'Found' if exists else 'Missing'}")
    return exists

def check_requirements():
    """Verify requirements.txt has all necessary packages"""
    required_packages = [
        'flask',
        'gunicorn',
        'pillow',
        'boto3',
        'pandas',
        'python-dotenv',
        'weasyprint'
    ]
    
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read().lower()
            
        print("\nChecking requirements.txt:")
        all_present = True
        for pkg in required_packages:
            present = pkg.lower() in content
            status = "[OK]" if present else "[FAIL]"
            print(f"  {status} {pkg}")
            if not present:
                all_present = False
        
        return all_present
    except FileNotFoundError:
        print("❌ requirements.txt not found!")
        return False

def check_procfile():
    """Verify Procfile configuration"""
    try:
        with open('Procfile', 'r') as f:
            content = f.read()
        
        print("\nChecking Procfile:")
        checks = [
            ('gunicorn' in content, 'Uses gunicorn'),
            ('app:app' in content, 'References app:app'),
            ('$PORT' in content or '${PORT}' in content, 'Uses $PORT variable'),
            ('0.0.0.0' in content, 'Binds to 0.0.0.0'),
        ]
        
        all_pass = True
        for check, description in checks:
            status = "[OK]" if check else "[FAIL]"
            print(f"  {status} {description}")
            if not check:
                all_pass = False
        
        return all_pass
    except FileNotFoundError:
        print("[FAIL] Procfile not found!")
        return False

def check_app_py():
    """Basic checks on app.py"""
    try:
        with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        print("\nChecking app.py:")
        checks = [
            ('Flask' in content, 'Imports Flask'),
            ('app = Flask' in content, 'Creates Flask app'),
            ('def ' in content, 'Has route functions'),
        ]
        
        all_pass = True
        for check, description in checks:
            status = "[OK]" if check else "[FAIL]"
            print(f"  {status} {description}")
            if not check:
                all_pass = False
        
        return all_pass
    except FileNotFoundError:
        print("[FAIL] app.py not found!")
        return False

def check_python_version():
    """Check Python version"""
    try:
        with open('runtime.txt', 'r') as f:
            version = f.read().strip()
        
        print(f"\nPython version: {version}")
        return True
    except FileNotFoundError:
        print("WARNING: No runtime.txt found (Railway will use default Python)")
        return True

def main():
    """Run all verification checks"""
    print("="*60)
    print("Railway Deployment Verification")
    print("="*60)
    
    print("\nChecking deployment files:")
    files_check = [
        check_file_exists('Procfile', required=True),
        check_file_exists('requirements.txt', required=True),
        check_file_exists('app.py', required=True),
        check_file_exists('runtime.txt', required=False),
        check_file_exists('railway.json', required=False),
        check_file_exists('nixpacks.toml', required=False),
    ]
    
    checks = [
        check_requirements(),
        check_procfile(),
        check_app_py(),
        check_python_version(),
    ]
    
    print("\n" + "="*60)
    
    if all(checks) and all(files_check):
        print("SUCCESS: ALL CHECKS PASSED! Ready to deploy!")
        print("\nNext steps:")
        print("  1. git add Procfile railway.json nixpacks.toml")
        print("  2. git commit -m 'Fix Railway deployment'")
        print("  3. git push origin main")
        print("  4. Monitor Railway dashboard for deployment")
        return 0
    else:
        print("FAILED: SOME CHECKS FAILED! Fix issues before deploying.")
        print("\nReview RAILWAY_DEPLOYMENT_FIX.md for solutions")
        return 1

if __name__ == "__main__":
    sys.exit(main())

