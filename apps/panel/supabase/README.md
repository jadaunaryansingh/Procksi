# Panel Portal Database Setup - SQL Scripts

## 📋 **Overview**

These SQL scripts will populate your Supabase database with test data for the Panel Portal. Run them in order to create a complete demo environment with teams in various evaluation states.

## 🎯 **What You'll Get**

- **20 Teams** with realistic names and projects
- **5 Teams** - Completed evaluations ✅
- **5 Teams** - Upcoming slots ⏰
- **3 Teams** - Active slots (can evaluate now!) 🔥
- **4 Teams** - Missed evaluations ❌
- **3 Teams** - No slots assigned yet

## 📝 **Step-by-Step Instructions**

### **1. Open Supabase SQL Editor**
1. Go to your [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project: `hchvwzrloimoyqmltvjc`
3. Click on **SQL Editor** in the left sidebar
4. Click **New Query**

### **2. Run Scripts in Order**

**Important:** Run each script one at a time, in the exact order below:

#### **Step 1: Clear Existing Data**
- Copy and paste content from: `001_clear_existing_data.sql`
- Click **Run**
- This removes all existing teams, projects, slots, and evaluations

#### **Step 2: Create Teams and Projects**
- Copy and paste content from: `002_create_teams_and_projects.sql`
- Click **Run**
- Creates 20 teams (IDs 101-120) with projects and GitHub data

#### **Step 3: Create Slots**
- Copy and paste content from: `003_create_slots.sql`
- Click **Run**
- Creates slots with different statuses for Panel P01

#### **Step 4: Create Evaluations**
- Copy and paste content from: `004_create_evaluations.sql`
- Click **Run**
- Creates evaluation records for submitted teams (101-105)

#### **Step 5: Create Alerts and User**
- Copy and paste content from: `005_create_alerts_and_user.sql`
- Click **Run**
- Creates alerts for missed teams and panel user account

#### **Step 6: Verify Setup**
- Copy and paste content from: `006_final_verification.sql`
- Click **Run**
- Displays summary of all created data and login credentials

## 🔑 **Login Credentials**

After running all scripts, use these credentials:

- **Email:** `panel01@gla.ac.in`
- **Password:** `panel123`
- **Panel ID:** `P01`

## ✅ **Expected Results**

### **Dashboard View:**
- Active slot indicator (1 of 3 teams)
- Progress tracker showing completed evaluations
- Real-time system clock and next upcoming slot

### **My Slots Page:**
- **Alpha Innovators** (101) → ✅ **Submitted**
- **Beta Developers** (102) → ✅ **Submitted**
- **Gamma Solutions** (103) → ✅ **Submitted**
- **Delta Coders** (104) → ✅ **Submitted**
- **Epsilon Tech** (105) → ✅ **Submitted**
- **Zeta Systems** (106) → ⏰ **Upcoming**
- **Eta Builders** (107) → ⏰ **Upcoming**
- **Theta Engineers** (108) → ⏰ **Upcoming**
- **Iota Creators** (109) → ⏰ **Upcoming**
- **Kappa Designers** (110) → ⏰ **Upcoming**
- **Lambda Squad** (111) → 🔥 **Active** (can evaluate now!)
- **Mu Developers** (112) → 🔥 **Active** (can evaluate now!)
- **Nu Architects** (113) → 🔥 **Active** (can evaluate now!)
- **Xi Programmers** (114) → ❌ **Missed**
- **Omicron Labs** (115) → ❌ **Missed**
- **Pi Solutions** (116) → ❌ **Missed**
- **Rho Innovators** (117) → ❌ **Missed**
- **Sigma Coders** (118) → No slot assigned
- **Tau Technologists** (119) → No slot assigned
- **Upsilon Makers** (120) → No slot assigned

### **Missed Submissions Page:**
- 4 teams showing as missed
- Can request reschedule for each team
- Download report functionality works

### **Active Evaluation:**
- Try evaluating teams **111**, **112**, or **113**
- Time-bound evaluation form with countdown timer
- Auto-save draft functionality
- Submit and get secure receipt

## 🔧 **Testing Checklist**

1. **Login** ✓ - Use panel01@gla.ac.in / panel123
2. **Dashboard** ✓ - Should show active slots and progress
3. **My Slots** ✓ - All teams visible with correct status
4. **Active Evaluation** ✓ - Evaluate one of the active teams
5. **Missed Submissions** ✓ - Request reschedule for a missed team
6. **Parameters** ✓ - View evaluation rubric
7. **Secure Receipt** ✓ - View receipt for submitted evaluation

## ⚠️ **Troubleshooting**

### **"relation does not exist" error**
- First apply the schema using `scripts/apply_supabase_schema.py`
- Or manually run the schema SQL from the migrations folder

### **"duplicate key value" error**
- Run `001_clear_existing_data.sql` first to clean up
- Make sure you're running scripts in the correct order

### **No data showing in frontend**
- Verify login credentials: panel01@gla.ac.in / panel123
- Check that Panel ID is "P01" in the application
- Ensure all scripts ran successfully without errors

### **Permission denied**
- Make sure you're running queries as the database owner
- Check RLS (Row Level Security) policies if data isn't visible

## 🎉 **Success!**

Once all scripts run successfully, you'll have a fully functional Panel Portal with realistic data for testing all features!

---
**Created for Panel Portal Project**
*Run in Supabase SQL Editor in the order specified above*