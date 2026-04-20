# Nikudot

Automatically marks Hebrew weekly care worker PDF timesheets.

## What it does

For each PDF it:
- Reads the weekly work schedule from the top table
- Places a **dot** on each working day in the monthly log
- Places a **dash** on holidays, and moves the dot to the next available free day
- Draws a **circle with X** on the patient signature cell for each week that had working days
- Marks the bottom declaration table based on the worker's family relation status

## How to use

1. Double-click `Nikudot.exe`
2. Click **Browse…** and select the folder containing the PDF files
3. Click **Start**
4. Marked files are saved to a `marked/` folder next to the originals
5. Any files that failed are copied to an `errors/` folder
6. When done the button changes to **Done ✓** — click it to close

## Download

Go to the [Actions](../../actions) tab → latest run → **Nikudot-Windows** artifact.
