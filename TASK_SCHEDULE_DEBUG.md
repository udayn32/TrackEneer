# 🔍 Tasks Not Showing in Today's Schedule - Complete Fix Guide

## ✅ What I Added to Help Debug

### 1. Frontend Logging
**File**: `client/app/page.jsx`

Added console logs to track:
- `📅 Loading Today's Schedule...` - When schedule loads
- `✅ Received tasks from Eisenhower endpoint: X tasks` - How many tasks loaded
- `❌ Failed to load prioritized schedule` - If there's an error

### 2. Backend Logging  
**File**: `server/scheduler.py`

Added print statements:
- `📊 Eisenhower endpoint called - Found X pending tasks` - When API is called
- `✅ WebSocket notification sent for new task: [title]` - When task created

### 3. Debug Endpoint
**New endpoint**: `http://localhost:5000/api/debug/tasks`

Returns:
```json
{
  "total_tasks": 5,
  "pending_tasks": 3,
  "today_tasks": 2,
  "today_date": "2025-10-02",
  "recent_tasks": [...]
}
```

---

## 🧪 Step-by-Step Testing

### Test 1: Check if Tasks are Being Created

1. **Open backend terminal** - should show:
   ```
   Uvicorn running on http://0.0.0.0:5000
   ```

2. **Open frontend** (http://localhost:3000)

3. **Open browser console** (Press F12)

4. **Enable notifications** (click bell icon)

5. **Add a task**:
   - Title: "Test Task 1"
   - Start time: 12:17
   - End time: 12:19

6. **Check backend terminal** for:
   ```
   ✅ WebSocket notification sent for new task: Test Task 1
   ```

7. **Check frontend console** for:
   ```
   📨 Real-time notification: {type: 'task_added', ...}
   ✅ Task added - refreshing UI
   📅 Loading Today's Schedule... (refreshTrigger: 1)
   ```

### Test 2: Check Database Contents

Visit: **http://localhost:5000/api/debug/tasks**

This will show:
- How many total tasks exist
- How many are pending
- How many are scheduled for today
- List of recent tasks

**Expected**: After adding a task, numbers should increase!

### Test 3: Check Eisenhower Endpoint Directly

Visit: **http://localhost:5000/api/schedule/eisenhower**

You should see JSON with:
```json
{
  "prioritized": [
    {
      "id": "...",
      "title": "Test Task 1",
      "startTime": "...",
      ...
    }
  ]
}
```

**If you see your task here** → Frontend issue
**If you DON'T see your task** → Backend issue

---

## 🐛 Common Issues & Solutions

### Issue 1: Tasks Created but Don't Appear

**Symptoms**:
- ✅ "WebSocket notification sent" in backend
- ✅ "Task added - refreshing UI" in frontend
- ❌ But task doesn't show in UI

**Possible Causes**:

**A. Backend returns tasks but frontend filters them out**
- Check console: "Received tasks from Eisenhower endpoint: 0 tasks"
- But backend says: "Found 3 pending tasks"
- **Fix**: Check if `data.prioritized` exists in response

**B. Frontend not calling refresh**
- Check if `refreshTrigger` increments in console
- Should go from 0 → 1 → 2 each time you add a task
- **Fix**: Make sure WebSocket calls `triggerRefresh()`

**C. Backend health check failing**
- Schedule only loads if `backendHealthy === true`
- Check console: `console.log('Backend healthy:', backendHealthy)`
- **Fix**: Restart backend if it's down

### Issue 2: WebSocket Not Sending Notifications

**Symptoms**:
- ❌ No "WebSocket notification sent" in backend
- ❌ No notification popup

**Debug**:
1. Check backend logs for WebSocket connection:
   ```
   WebSocket client connected. Total: 1
   ```

2. Check frontend console for:
   ```
   🔌 Connecting to WebSocket: ws://localhost:5000/ws/notifications
   ✅ WebSocket connected - real-time notifications active
   ```

**Fix**: 
- Make sure notifications are enabled (bell icon)
- Refresh the page
- Check if backend is running

### Issue 3: Wrong Time Display (12:17 shows as 5:45)

**This was already fixed!**
- Uses `+05:30` timezone offset explicitly
- All times stored and displayed in IST

---

## 📊 What Should Happen (Correct Flow)

```
User clicks "Add Task"
  ↓
Frontend sends: POST /api/add-task
  ↓
Backend creates task in Neo4j database
  ↓
Backend prints: "✅ WebSocket notification sent for new task"
  ↓
Backend sends WebSocket message to frontend
  ↓
Frontend receives: {type: 'task_added', title: '...'}
  ↓
Frontend prints: "✅ Task added - refreshing UI"
  ↓
Frontend calls: triggerRefresh()
  ↓
refreshTrigger changes: 0 → 1
  ↓
useEffect triggers (depends on refreshTrigger)
  ↓
Frontend prints: "📅 Loading Today's Schedule... (refreshTrigger: 1)"
  ↓
Frontend calls: GET /api/schedule/eisenhower
  ↓
Backend prints: "📊 Eisenhower endpoint called - Found X pending tasks"
  ↓
Backend returns: {prioritized: [{...}]}
  ↓
Frontend prints: "✅ Received tasks from Eisenhower endpoint: X tasks"
  ↓
Frontend calls: setTasks(data.prioritized)
  ↓
UI updates: Task appears in "Today's Schedule"
```

---

## 🔍 Quick Diagnostics

### Run These Commands:

**1. Check if backend is running:**
```powershell
curl http://localhost:5000/api/health
```
Should return: `{"status": "ok"}`

**2. Check database state:**
```powershell
curl http://localhost:5000/api/debug/tasks
```
Should show task count and recent tasks

**3. Check Eisenhower endpoint:**
```powershell
curl http://localhost:5000/api/schedule/eisenhower
```
Should return tasks in `prioritized` array

---

## 📝 What to Check Next

Open browser console and add a task, then report:

1. **Backend Terminal**:
   - [ ] Shows "✅ WebSocket notification sent"
   - [ ] Shows "📊 Eisenhower endpoint called"
   - [ ] Number of tasks found: _______

2. **Frontend Console**:
   - [ ] Shows "📨 Real-time notification"
   - [ ] Shows "✅ Task added - refreshing UI"
   - [ ] Shows "📅 Loading Today's Schedule"
   - [ ] refreshTrigger value: _______
   - [ ] Shows "✅ Received X tasks"
   - [ ] Number of tasks received: _______

3. **Debug Endpoint** (http://localhost:5000/api/debug/tasks):
   - total_tasks: _______
   - pending_tasks: _______
   - today_tasks: _______

4. **UI**:
   - [ ] Task appears in "Today's Schedule"
   - [ ] Task shows correct time (12:17, not 5:45)

---

## 🎯 Most Likely Cause

Based on your description, the most likely issue is:

**The Eisenhower endpoint returns all pending tasks, but the frontend might be filtering or the response format changed.**

Check the frontend console for the exact number of tasks received. If it says "Received 0 tasks" but backend says "Found 3 tasks", then there's a response parsing issue.

---

## 🔧 Quick Fix to Try

If tasks are being created but not showing, try this manual refresh:

**In browser console**, paste:
```javascript
// Force reload the schedule
window.location.reload();
```

Or click the "Refresh" button in the error message (if backend shows not ready).

---

## 📚 Documentation Created

1. **NOTIFICATION_FIX.md** - How notifications work
2. **DEBUG_SCHEDULE.md** - This file - debugging tasks not appearing

All IST timezone fixes are already in place! 🇮🇳

---

**Next Step**: Add a task and share the console output from both frontend and backend!
