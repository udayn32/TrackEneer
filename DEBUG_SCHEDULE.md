# 🔍 Debug Guide - Tasks Not Appearing in Today's Schedule

## What I Added

### Frontend Logging (client/app/page.jsx)
Added console.log statements to track:
- When schedule loads: `📅 Loading Today's Schedule...`
- Number of tasks received: `✅ Received tasks from Eisenhower endpoint: X tasks`
- Errors: `❌ Failed to load prioritized schedule`

### Backend Logging (server/scheduler.py)
Added print statement in Eisenhower endpoint:
- `📊 Eisenhower endpoint called - Found X pending tasks`

---

## 🧪 How to Debug

### Step 1: Check if Task is Created
1. **Add a task** through the UI
2. **Check backend terminal** for:
   ```
   ✅ WebSocket notification sent for new task: Test Task
   ```
3. **Check frontend console** (F12) for:
   ```
   📨 Real-time notification: {type: 'task_added', taskId: '...', title: 'Test Task'}
   ✅ Task added - refreshing UI
   ```

### Step 2: Check if Schedule Reloads
Frontend console should show:
```
📅 Loading Today's Schedule... (refreshTrigger: 1)
```
The number should increment each time you add a task.

### Step 3: Check Backend Response
Frontend console should show:
```
✅ Received tasks from Eisenhower endpoint: 3 tasks
```

Backend terminal should show:
```
📊 Eisenhower endpoint called - Found 3 pending tasks
```

---

## 🐛 Possible Issues & Solutions

### Issue 1: "refreshTrigger" Not Incrementing
**Symptom**: Console shows same refreshTrigger value
**Cause**: `triggerRefresh()` not being called
**Check**: 
- Is WebSocket connected? Look for "✅ WebSocket connected"
- Is notification handler running? Look for "📨 Real-time notification"

### Issue 2: Backend Returns 0 Tasks
**Symptom**: "Found 0 pending tasks" in backend
**Cause**: Tasks not being saved to database
**Debug**:
```bash
# Check Neo4j directly (if you have neo4j browser access)
# Or add this endpoint to server/scheduler.py:

@app.get('/api/debug/tasks')
async def debug_tasks():
    with driver.session() as session:
        result = session.run("MATCH (t:Task) RETURN t.id, t.title, t.status, t.startTime")
        tasks = [dict(r) for r in result]
    return {'total': len(tasks), 'tasks': tasks}
```

Then visit: http://localhost:5000/api/debug/tasks

### Issue 3: Backend Returns Tasks but Frontend Shows 0
**Symptom**: Backend says "Found 3 tasks" but frontend shows "0 tasks"
**Cause**: Response parsing issue
**Check**:
- Frontend console for the actual response
- Add: `console.log('Raw response:', data)` before `setTasks(data.prioritized)`

### Issue 4: Tasks Created with Wrong Status
**Symptom**: Tasks are created but status is not 'pending'
**Check**: 
- Look in add_task response for status field
- Should be `status: 'pending'` in the CREATE query

---

## 🔬 Manual Testing Commands

### Test 1: Check if Backend is Receiving Requests
```bash
# In PowerShell while backend is running
curl http://localhost:5000/api/schedule/eisenhower
```

Should return JSON with `prioritized: [...]`

### Test 2: Check Task Count in Database
Add this debug endpoint to `server/scheduler.py`:

```python
@app.get('/api/debug/task-count')
async def debug_task_count():
    with driver.session() as session:
        # Count all tasks
        total = session.run("MATCH (t:Task) RETURN count(t) as count").single()['count']
        
        # Count pending tasks
        pending = session.run("MATCH (t:Task) WHERE t.status = 'pending' RETURN count(t) as count").single()['count']
        
        # Count today's tasks
        today = datetime.now().date()
        today_tasks = session.run(
            "MATCH (:Day {date: date($d)})-[:HAS_TASK]->(t:Task) RETURN count(t) as count",
            d=today
        ).single()['count']
    
    return {
        'total_tasks': total,
        'pending_tasks': pending,
        'today_tasks': today_tasks,
        'today_date': str(today)
    }
```

Then visit: http://localhost:5000/api/debug/task-count

---

## 📊 Expected Flow

```
1. User adds task
   ↓
2. Backend creates task in Neo4j
   ↓
3. Backend sends WebSocket notification
   ↓
4. Frontend receives WebSocket message
   ↓
5. Frontend calls triggerRefresh()
   ↓
6. refreshTrigger increments (e.g., 0 → 1)
   ↓
7. useEffect detects change
   ↓
8. Frontend calls api.getEisenhower()
   ↓
9. Backend returns all pending tasks
   ↓
10. Frontend updates UI with tasks
```

---

## 🎯 Quick Test Script

Add this to a file: `test-task-creation.md`

```markdown
1. Open http://localhost:3000
2. Open browser console (F12)
3. Enable notifications (click bell icon)
4. Add a task:
   - Title: "Debug Test Task"
   - Start: Current time
   - End: +5 minutes
5. Click Add

Expected logs in order:
- Frontend: "📨 Real-time notification: ..."
- Frontend: "✅ Task added - refreshing UI"
- Frontend: "📅 Loading Today's Schedule... (refreshTrigger: 1)"
- Backend: "📊 Eisenhower endpoint called - Found X pending tasks"
- Frontend: "✅ Received tasks from Eisenhower endpoint: X tasks"

If you see all these logs but task still doesn't appear:
- Check if X is increasing (means task was saved)
- Check if prioritized array is empty (response parsing issue)
- Check browser network tab for the actual API response
```

---

## 🔧 Quick Fixes to Try

### Fix 1: Force Refresh After Task Creation
In `client/app/page.jsx`, find the `AddTaskModal` component and ensure it calls `onTaskAdded` in the success handler:

```javascript
await api.addTask({...});
onTaskAdded(); // This should trigger refresh
onClose();
```

### Fix 2: Verify Backend Health State
The schedule won't load if `backendHealthy` is false. Check:
```javascript
// In browser console:
console.log('Backend healthy:', backendHealthy);
```

### Fix 3: Check Date Matching
The issue might be date timezone mismatch. Check:
```javascript
// In browser console:
const today = new Date().toISOString().split('T')[0];
console.log('Today:', today); // Should be 2025-10-02
```

---

## 📝 What to Report Back

Please check and report:
1. ✅ or ❌ "WebSocket notification sent" appears in backend
2. ✅ or ❌ "Task added - refreshing UI" appears in frontend
3. ✅ or ❌ "refreshTrigger" value increments
4. ✅ or ❌ "Eisenhower endpoint called" appears in backend
5. Number shown: "Found X pending tasks" (X = ?)
6. Number shown: "Received X tasks" in frontend (X = ?)
7. ✅ or ❌ Tasks actually appear in UI

This will help identify exactly where the issue is!
