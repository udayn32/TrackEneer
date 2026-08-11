# 🔔 Notification & Task System - Testing Guide

## ✅ What Was Fixed

### 1. **WebSocket Payload Mismatch** (CRITICAL FIX)
**Problem**: Frontend was looking for `data.task.title` but backend was sending `data.title`
**Solution**: Updated WebSocket handler to check both formats:
- `data.title` (primary - from backend)
- `data.task?.title` (fallback - for compatibility)

### 2. **Enhanced Backend Notifications**
**Added**: Complete task information in WebSocket payload:
```javascript
{
  type: 'task_added',
  taskId: '...',
  title: 'Task Title',
  description: 'Task Description',
  startTime: '2025-10-02T12:17:00+05:30' (IST),
  endTime: '2025-10-02T12:19:00+05:30' (IST),
  task: { /* full task object */ }
}
```

### 3. **IST Timezone**
All times are in Indian Standard Time (UTC+5:30):
- Task creation sends: `2025-10-02T12:17:00+05:30`
- Backend stores in IST
- Frontend displays in IST

---

## 🧪 How to Test

### Test 1: Task Creation Notification
1. **Start Backend**: `cd server && python scheduler.py`
2. **Start Frontend**: `cd client && npm run dev`
3. **Open**: http://localhost:3000
4. **Enable Notifications**: Click bell icon (allow permissions)
5. **Add Task**:
   - Title: "Test Task"
   - Start: Current time
   - End: +2 minutes
6. **Expected**:
   - ✅ Notification pops up: "NEW TASK ADDED! 📝 Test Task"
   - ✅ Task appears in schedule immediately
   - ✅ Console shows: "✅ Task added - refreshing UI"

### Test 2: Start Time Notification
1. Create a task that starts in **30 seconds**
2. **Expected**:
   - After ~30 seconds: "🚀 START NOW! ⏰ Test Task - Let's do this! 💪"
   - Notification stays visible (requireInteraction: true)

### Test 3: End Time Notification
1. Create a task that ends in **1 minute**
2. **Expected**:
   - After ~1 minute: "🏁 TASK COMPLETED! ✨ Test Task - Great work! 🎉"

### Test 4: Deadline Notification
1. Create a task with due date in **5 minutes**
2. **Expected**:
   - At 5 min: "📅 Upcoming Deadline: Test Task - Due in X minutes (HH:MM AM/PM IST)"
   - At 1 min: "⏰ URGENT: Test Task - Deadline in X minutes (HH:MM AM/PM IST)"
   - At 0 min: "🚨 DEADLINE NOW: Test Task - Deadline is right now!"

---

## 🔍 Debugging

### Check WebSocket Connection
1. Open browser console (F12)
2. Look for:
   ```
   🔌 Connecting to WebSocket: ws://localhost:5000/ws/notifications
   ✅ WebSocket connected - real-time notifications active
   ```

### Check Task Creation
1. Add a task
2. Console should show:
   ```
   📨 Real-time notification: {type: 'task_added', taskId: '...', title: 'Test Task'}
   ✅ Task added - refreshing UI
   ```

### Check Backend Logs
Backend console should show:
```
WebSocket client connected. Total: 1
✅ WebSocket notification sent for new task: Test Task
```

---

## 🐛 Common Issues

### Issue 1: No "NEW TASK ADDED" Notification
**Cause**: WebSocket not connected
**Fix**: 
1. Enable notifications FIRST (bell icon)
2. Check backend is running
3. Refresh page

### Issue 2: Task Not Appearing After Creation
**Cause**: triggerRefresh not working
**Fix**: Already fixed - WebSocket handler calls `triggerRefresh()`

### Issue 3: Wrong Time Display (5:45 instead of 12:17)
**Cause**: Timezone conversion issue
**Fix**: Already fixed - using `+05:30` offset explicitly
```javascript
convertToIST(date, time) {
  return `${date}T${time}:00+05:30`; // Explicit IST
}
```

### Issue 4: Notifications Not Appearing at All
**Check**:
1. Browser permissions: Settings → Site Settings → Notifications → Allow
2. Notification toggle: Bell icon should be solid (not bell-off)
3. Backend health: Should say nothing when healthy (no error message)

---

## 🎯 Expected Behavior

### ✅ When Adding Task at 12:17 PM:
1. You enter: `12:17` in time field
2. Frontend sends: `2025-10-02T12:17:00+05:30`
3. Backend receives and stores in IST
4. WebSocket broadcasts: `{type: 'task_added', title: 'Your Task'}`
5. Frontend shows notification: "✅ NEW TASK ADDED!"
6. Task appears in schedule showing: `12:17 PM`
7. UI refreshes automatically

### ✅ Notification Types You'll See:
- 🎯 **On Enable**: "Notifications Enabled! Real-time updates active"
- ✅ **On Task Add**: "NEW TASK ADDED! 📝 [Task Title]"
- 🚀 **On Task Start**: "START NOW! ⏰ [Task Title]"
- 🏁 **On Task End**: "TASK COMPLETED! ✨ [Task Title]"
- ⏰ **On Deadline**: Various urgency levels (15min, 1hr, 3hr, today)

---

## 🌏 IST Timezone Format

All times are displayed with IST indicator:
- **Time Format**: `02:30 PM IST`
- **Date Format**: `10/2/2025, 02:30 PM`
- **ISO Format**: `2025-10-02T14:30:00+05:30`

---

## 🔄 Refresh Behavior

**Auto-refresh removed** - now only refreshes on:
- ✅ Task created
- ✅ Task updated
- ✅ WebSocket notification received
- 30-second polling for notifications (reduced from 1 second)

**No more constant "loading"** - page stays stable! 🎉

---

## 📊 Monitoring

### Browser Console Commands
```javascript
// Check if notifications are enabled
localStorage.getItem('notificationsEnabled')

// Test notification manually
new Notification('Test', {body: 'Testing notifications'})

// Check WebSocket state
// (Look for WebSocket object in Network tab)
```

### Backend Health Check
```bash
curl http://localhost:5000/api/health
# Should return: {"status": "ok", ...}
```

---

## ✨ Summary

**What Works Now**:
1. ✅ Task creation notifications appear instantly
2. ✅ Tasks show up in UI immediately after creation
3. ✅ Correct IST time display (12:17 shows as 12:17)
4. ✅ Start/End/Deadline notifications
5. ✅ No excessive refreshing (95% reduction in API calls)
6. ✅ WebSocket real-time updates
7. ✅ IST timezone throughout the system

**Key Files Updated**:
- `client/app/page.jsx` - WebSocket payload handling
- `server/scheduler.py` - Enhanced notification payload

**Test it now!** 🚀
