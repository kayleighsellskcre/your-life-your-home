# Equity Overview - Homebot-Style Feature

## Overview
The Equity Overview page now provides comprehensive loan management and personalized mortgage savings tips, similar to Homebot.

## Features

### 1. **Visual Equity Display**
- Three beautiful gradient cards showing:
  - Estimated home value
  - Current loan balance  
  - Your equity (with LTV ratio and payoff date)

### 2. **Loan Information Form**
Enter and update your complete loan details:
- Current home value
- Current loan balance
- Interest rate (%)
- Monthly payment
- Loan term (15, 20, or 30 years)
- Loan start date

The form auto-populates with your existing data and saves updates to the database.

### 3. **Smart Tips & Savings Strategies**
Receive personalized mortgage tips based on your situation:

- **High Interest Rate (>6.5%)**: Suggests refinancing to lower monthly payments
- **Long Term Remaining (>20 years) + High Equity**: Recommends extra principal payments to save on interest
- **Low LTV (<80%)**: Alerts you about potential PMI removal
- **High Equity (>$100k)**: Highlights opportunities for renovations, debt consolidation, or investments

### 4. **Automatic Calculations**
The system automatically computes:
- **Equity**: Home value minus loan balance
- **LTV (Loan-to-Value)**: Percentage of home financed
- **Payoff Date**: Estimated mortgage completion date
- **Years Remaining**: Time left on your loan

## Database Changes

### New Columns Added to `homeowner_snapshots`:
- `loan_term_years` (REAL) - Length of loan in years (15, 20, 30)
- `loan_start_date` (TEXT) - When the loan originated

### New Function Added:
**`upsert_homeowner_snapshot_full()`**
- Accepts optional parameters for all snapshot fields
- Merges new data with existing values
- Auto-calculates equity when both value and balance are present
- Updates timestamp on every save

## Route Updates

**`/homeowner/value/equity-overview`** now supports:
- **GET**: Displays current data with calculated metrics and tips
- **POST**: Saves updated loan information from the form

## Usage

1. Navigate to **Value > Equity Overview** in the homeowner dashboard
2. Enter your loan details in the form
3. Click **"Save Loan Details"**
4. View your personalized tips and updated equity metrics
5. Return anytime to update values as your situation changes

## Benefits

✨ **Clear Financial Picture**: See exactly where you stand with your home equity
💡 **Actionable Insights**: Get specific suggestions to save money
📊 **Track Progress**: Monitor equity growth and payoff timeline
🎯 **Make Informed Decisions**: Understand opportunities for refinancing, PMI removal, or equity utilization

---

*All calculations are estimates. Consult with your lender for exact figures.*
