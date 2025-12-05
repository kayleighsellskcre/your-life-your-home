# Automatic Home Value Appreciation System

## Overview
The platform now automatically appreciates home values over time at a rate of **3.5% annually** (within the 3-4% range requested). This eliminates the need for manual refresh buttons and provides continuously updated home values based on time elapsed since purchase.

## How It Works

### 1. **Database Storage**
- `initial_purchase_value`: The original purchase price of the home (baseline for appreciation)
- `loan_start_date`: The purchase/loan start date (used to calculate time elapsed)
- `value_estimate`: Current estimated value (auto-calculated, not stored permanently)

### 2. **Automatic Calculation**
Every time a user views their dashboard, the system:
1. Retrieves the `initial_purchase_value` and `loan_start_date`
2. Calculates years elapsed since purchase
3. Applies compound appreciation: `Value = Initial × (1.035)^years`
4. Displays the appreciated value in real-time

### 3. **Formula Details**
```python
def calculate_appreciated_value(initial_value, purchase_date, annual_rate=0.035):
    years_elapsed = (today - purchase_date).days / 365.25
    appreciated_value = initial_value * ((1 + annual_rate) ** years_elapsed)
    return appreciated_value
```

### 4. **Example Calculation**
- **Initial Purchase**: $480,000 (May 30, 2019)
- **Years Elapsed**: 6.52 years (as of Dec 2025)
- **Annual Rate**: 3.5%
- **Current Value**: $600,612
- **Total Appreciation**: $120,612 (25.1%)

## Benefits

✅ **Always Up-to-Date**: Values update automatically every time the page loads
✅ **No Manual Refresh**: Eliminates the need for "refresh value" buttons
✅ **Consistent Growth**: 3.5% annual rate provides steady, realistic appreciation
✅ **Automatic Equity Updates**: Equity is recalculated based on appreciated value
✅ **Clean UI**: Simplified dashboard without refresh options

## User Experience Changes

### Before
- Users had to click "Refresh value" button
- Value remained static until manually refreshed
- Confusing when last updated

### After
- Values automatically update based on time
- No user action required
- Always reflects current market appreciation
- Cleaner card design with single "Get detailed report" link

## Technical Implementation

### Files Modified
1. **`app.py`**
   - Added `calculate_appreciated_value()` function
   - Updated `get_homeowner_snapshot_or_default()` to apply appreciation
   - Removed `refresh_home_value()` route

2. **`database.py`**
   - Added `initial_purchase_value` column migration
   - Maintains baseline for appreciation calculations

3. **`templates/homeowner/overview.html`**
   - Removed "Refresh value" link
   - Simplified Home Value card UI

4. **`scripts/set_initial_home_values.py`**
   - Migration script to set initial values for existing records

## Customization Options

### Adjusting the Rate
To change the annual appreciation rate, edit `app.py`:
```python
# Current: 3.5% annual (middle of 3-4% range)
value_estimate = calculate_appreciated_value(
    initial_value, 
    snap["loan_start_date"],
    annual_rate=0.035  # Change this value
)
```

**Rate Examples:**
- `0.030` = 3.0% annual
- `0.035` = 3.5% annual (current)
- `0.040` = 4.0% annual

### Future Enhancements
- Regional appreciation rates (different rates by ZIP code)
- Market-based adjustments (bull/bear market multipliers)
- Integration with real estate APIs for live market data
- User-customizable appreciation assumptions

## Testing

Run the test script to verify calculations:
```bash
python scripts/test_appreciation.py
```

This displays:
- Current snapshot data
- Years elapsed since purchase
- Appreciated value calculation
- Current equity position

## Maintenance

### Setting Initial Values for New Users
When users first enter their home data:
- `value_estimate` should be set to current home value
- `initial_purchase_value` should be set to actual purchase price
- `loan_start_date` should be set to purchase date

The system will then automatically appreciate from the initial value forward.

### Updating Baseline Values
If a user gets a professional appraisal or reassessment:
1. Update `initial_purchase_value` to the new baseline
2. Update `loan_start_date` to the reassessment date
3. Future appreciation will calculate from this new baseline

## Support & Questions

For questions about the automatic appreciation system:
- Check calculation accuracy with `scripts/test_appreciation.py`
- Verify database values: `initial_purchase_value`, `loan_start_date`
- Confirm annual rate is set to 0.035 in `calculate_appreciated_value()`

---

**Implementation Date**: December 4, 2025
**Version**: 1.0
**Rate**: 3.5% annually (compound)
