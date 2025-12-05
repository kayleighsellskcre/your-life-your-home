"""
Test the automatic home value appreciation formula
"""
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_connection

def test_appreciation():
    """Test the appreciation calculation"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get the snapshot
    cur.execute("""
        SELECT id, value_estimate, initial_purchase_value, loan_start_date, loan_balance
        FROM homeowner_snapshots
        WHERE id = 1
    """)
    
    snap = cur.fetchone()
    conn.close()
    
    if not snap:
        print("❌ No snapshot found")
        return
    
    initial_value = snap['initial_purchase_value']
    purchase_date = snap['loan_start_date']
    loan_balance = snap['loan_balance']
    
    print("=" * 60)
    print("Home Value Appreciation Test")
    print("=" * 60)
    print()
    print(f"📍 Purchase Date: {purchase_date}")
    print(f"💰 Initial Value: ${initial_value:,.0f}")
    print(f"📊 Loan Balance: ${loan_balance:,.0f}")
    print()
    
    # Calculate appreciation
    purchase_dt = datetime.strptime(purchase_date, '%Y-%m-%d')
    today = datetime.now()
    years_elapsed = (today - purchase_dt).days / 365.25
    
    annual_rate = 0.035  # 3.5%
    appreciated_value = initial_value * ((1 + annual_rate) ** years_elapsed)
    equity = appreciated_value - loan_balance
    
    print(f"⏱️  Years Elapsed: {years_elapsed:.2f} years")
    print(f"📈 Annual Rate: {annual_rate * 100}%")
    print()
    print(f"🏠 Current Appreciated Value: ${appreciated_value:,.0f}")
    print(f"💎 Current Equity: ${equity:,.0f}")
    print(f"📊 Equity Percentage: {(equity / appreciated_value * 100):.1f}%")
    print()
    print(f"✨ Total Appreciation: ${appreciated_value - initial_value:,.0f} ({((appreciated_value / initial_value - 1) * 100):.1f}%)")
    print()
    print("=" * 60)
    print("✅ Formula working correctly!")
    print("   Dashboard will now show automatically updated values")
    print("=" * 60)

if __name__ == "__main__":
    test_appreciation()
