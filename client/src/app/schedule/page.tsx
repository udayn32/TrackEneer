"use client";

import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";
import { useSession } from "next-auth/react";
import Image from "next/image";

const API_BASE = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, "") || "http://localhost:5000";

const fallbackAvatar = "https://avatars.dicebear.com/api/miniavs/trackeneer.svg";

type Quote = {
  content: string;
  author?: string;
};

type Task = {
  id?: string;
  title?: string;
  description?: string;
  startTime?: string | null;
  endTime?: string | null;
  dueDate?: string | null;
  priority?: string | null;
  category?: string | null;
};

type DeadlineEntry = {
  title?: string;
  dueDate?: string;
  priority?: string;
};

type Recommendation = {
  label: string;
  type?: string;
  estimate_minutes?: number;
  taskId?: string;
  taskTitle?: string;
};

type PendingNotification = {
  id: string;
  title?: string;
  type?: string;
  minutesUntil?: number;
  scheduledTime?: string;
  dueTime?: string;
};

type LiveNotification = {
  id: string;
  label: string;
  timestamp: string;
};

const formatToIST = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatLongDate = (date: Date) => {
  const formatter = new Intl.DateTimeFormat("en-IN", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });

  const parts = formatter.formatToParts(date).reduce<Record<string, string>>((acc, part) => {
    if (part.type !== "literal") {
      acc[part.type] = part.value;
    }
    return acc;
  }, {});

  const weekday = parts.weekday ?? "";
  const day = parts.day ?? "";
  const month = parts.month ?? "";
  const year = parts.year ?? "";

  return `${weekday} ${day} ${month} ${year}`.replace(/\s+/g, " ").trim();
};

const formatDueDate = (value?: string | null) => {
  if (!value) return "TBD";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "TBD";
  return formatLongDate(parsed);
};

const SchedulePage = () => {
  const { data: session } = useSession();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [deadlines, setDeadlines] = useState<DeadlineEntry[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [notifications, setNotifications] = useState<LiveNotification[]>([]);
  const [pendingNotifications, setPendingNotifications] = useState<PendingNotification[]>([]);
  const [eisenhower, setEisenhower] = useState<any | null>(null);
  const [eisenhowerMatrix, setEisenhowerMatrix] = useState<any | null>(null);
  const [loadingEisenhower, setLoadingEisenhower] = useState(true);
  const [showEisenhowerModal, setShowEisenhowerModal] = useState(false);
  const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [notifError, setNotifError] = useState<string | null>(null);
  const [loading, setLoading] = useState({ tasks: true, deadlines: true, quote: true, recs: true, pending: true });
  const [error, setError] = useState<string | null>(null);
  const [openForm, setOpenForm] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    startTime: "",
    endTime: "",
    dueDate: "",
  });

  const today = useMemo(() => new Date(), []);

  useEffect(() => {
    const controller = new AbortController();

    const fetchQuote = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/quote`, { signal: controller.signal });
        if (!response.ok) throw new Error("Failed to fetch quote");
        setQuote(await response.json());
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((prev) => prev ?? "Unable to load the entire schedule view.");
        }
      } finally {
        setLoading((prev) => ({ ...prev, quote: false }));
      }
    };

    const fetchTasks = async () => {
      try {
        const formatted = today.toISOString().split("T")[0];
        const response = await fetch(`${API_BASE}/api/schedule?date=${formatted}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Failed to fetch tasks");
        const data = await response.json();
        setTasks(Array.isArray(data.tasks) ? data.tasks : []);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((prev) => prev ?? "Unable to load the entire schedule view.");
        }
      } finally {
        setLoading((prev) => ({ ...prev, tasks: false }));
      }
    };

    const fetchDeadlines = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/upcoming-deadlines`, { signal: controller.signal });
        if (!response.ok) throw new Error("Failed to fetch deadlines");
        const data = await response.json();
        setDeadlines(Array.isArray(data.deadlines) ? data.deadlines : []);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((prev) => prev ?? "Unable to load the entire schedule view.");
        }
      } finally {
        setLoading((prev) => ({ ...prev, deadlines: false }));
      }
    };

    const fetchRecommendations = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/recommend-tasks`, { signal: controller.signal });
        if (!response.ok) throw new Error("Failed to fetch recommendations");
        const data = await response.json();
        setRecommendations(Array.isArray(data.recommendations) ? data.recommendations : []);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError((prev) => prev ?? "Unable to load the entire schedule view.");
        }
      } finally {
        setLoading((prev) => ({ ...prev, recs: false }));
      }
    };

    const fetchPendingNotifications = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/notifications/pending`, { signal: controller.signal });
        if (!response.ok) throw new Error("Failed to fetch notifications");
        const data = await response.json();
        setPendingNotifications(Array.isArray(data.notifications) ? data.notifications : []);
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setNotifError((prev) => prev ?? "Unable to load notifications.");
        }
      } finally {
        setLoading((prev) => ({ ...prev, pending: false }));
      }
    };

    const fetchEisenhower = async () => {
      try {
        setLoadingEisenhower(true);
        const res = await fetch(`${API_BASE}/api/schedule/eisenhower` , { signal: controller.signal });
        if (!res.ok) throw new Error('Failed to fetch eisenhower');
        const data = await res.json();
        setEisenhower(data);
      } catch (err) {
        // ignore silently, UI will simply show no data
      } finally {
        setLoadingEisenhower(false);
      }
    };

    const fetchEisenhowerMatrix = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/schedule/eisenhower/matrix`, { signal: controller.signal });
        if (!res.ok) throw new Error('Failed to fetch eisenhower matrix');
        const data = await res.json();
        setEisenhowerMatrix(data);
      } catch (err) {
        // ignore
      }
    };

    fetchQuote();
    fetchTasks();
    fetchDeadlines();
    fetchRecommendations();
    fetchPendingNotifications();
  fetchEisenhower();
  fetchEisenhowerMatrix();

    return () => controller.abort();
  }, [today]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const wsUrl = API_BASE.startsWith("https")
      ? API_BASE.replace(/^https/, "wss")
      : API_BASE.replace(/^http/, "ws");

    let socket: WebSocket | null = new WebSocket(`${wsUrl}/ws/notifications`);

    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (!data || typeof data !== "object") return;
        if (data.type === "ack") return;

        const ts = new Date().toISOString();
        let label = "";
        if (data.type === "task_start") {
          label = `Task "${data.task?.title ?? "Task"}" is starting`;
        } else if (data.type === "task_end") {
          label = `Task "${data.task?.title ?? "Task"}" is ending`;
        } else if (data.type === "task_due") {
          label = `Task "${data.task?.title ?? "Task"}" is due`;
        } else if (data.message) {
          label = String(data.message);
        } else {
          label = `Notification received (${data.type ?? "update"})`;
        }

  const idBase = data.task?.id ? `${data.task.id}-${data.type ?? "event"}` : `${data.type}-${ts}`;
        setNotifications((prev) => {
          const exists = prev.find((item) => item.id === idBase);
          const next = [
            { id: idBase, label, timestamp: ts },
            ...prev.filter((item) => item.id !== idBase),
          ];
          if (!exists && data.task?.id) {
            return next.slice(0, 10);
          }
          return next.slice(0, 10);
        });
      } catch (err) {
        console.error("Failed to parse notification", err);
      }
    };

    socket.addEventListener("open", () => {
      setWsStatus("open");
      try {
        socket?.send(JSON.stringify({ type: "ready" }));
      } catch (err) {
        console.error("Failed to send ready signal", err);
      }
    });
    socket.addEventListener("message", handleMessage);
    socket.addEventListener("close", () => {
      setWsStatus("closed");
    });
    socket.addEventListener("error", () => {
      setWsStatus("closed");
    });

    return () => {
      socket?.removeEventListener("message", handleMessage);
      socket?.close();
      socket = null;
    };
  }, []);

  // Register service worker and subscribe to push notifications (client-side)
  useEffect(() => {
    if (typeof window === "undefined" || !('serviceWorker' in navigator) || !('PushManager' in window)) return;

    let mounted = true;

    const ensureSwAndSubscribe = async () => {
      try {
        // register service worker
        const reg = await navigator.serviceWorker.register('/sw.js');
        console.log('Service worker registered (client):', reg.scope);

        // get vapid key from notification service
        const res = await fetch((process.env.NEXT_PUBLIC_NOTIFICATION_SERVICE || 'http://localhost:3001') + '/vapid-public-key');
        if (!res.ok) throw new Error('Failed to get VAPID key');
        const body = await res.json();
        const vapidKey = body.publicKey;
        if (!vapidKey) throw new Error('VAPID key not available');
        // Request permission if needed
        if (Notification.permission === 'default') {
          const perm = await Notification.requestPermission();
          if (perm !== 'granted') {
            console.warn('Notification permission denied by user');
            return;
          }
        } else if (Notification.permission === 'denied') {
          console.warn('Notification permission previously denied');
          return;
        }

        const existing = await reg.pushManager.getSubscription();
        let sub = existing;
        if (!existing) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidKey)
          });
        }

        if (sub && mounted) {
          console.log('Push subscription obtained (client)', sub.endpoint);
          // send to backend notification service and log response
          try {
            const r = await fetch((process.env.NEXT_PUBLIC_NOTIFICATION_SERVICE || 'http://localhost:3001') + '/subscribe', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ subscription: sub, userId: 'guest' })
            });
            if (!r.ok) {
              console.warn('Subscription POST failed', r.status, await r.text());
            } else {
              console.log('Subscription registered with notification service');
            }
          } catch (err) {
            console.warn('Failed to POST subscription to notification-service', err);
          }
        }
      } catch (err) {
        console.warn('Push setup failed (client):', err);
      }
    };

    ensureSwAndSubscribe();

    return () => { mounted = false; };
  }, []);

  function urlBase64ToUint8Array(base64String: string) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  const handleChange = (field: string) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const resetForm = () => {
    setForm({ title: "", description: "", startTime: "", endTime: "", dueDate: "" });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAdding(true);
    setError(null);

    const payload = {
      title: form.title,
      description: form.description,
      startTime: form.startTime ? new Date(form.startTime).toISOString() : null,
      endTime: form.endTime ? new Date(form.endTime).toISOString() : null,
      dueDate: form.dueDate ? new Date(form.dueDate).toISOString() : null,
    };

    try {
      const response = await fetch(`${API_BASE}/api/add-task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error("Failed to add task");

      setOpenForm(false);
      resetForm();
      // Refresh tasks and deadlines to keep UI in sync without waiting for next effect run.
      Promise.all([
        fetch(`${API_BASE}/api/schedule?date=${today.toISOString().split("T")[0]}`)
          .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Failed to refresh tasks"))))
          .then((data) => setTasks(Array.isArray(data.tasks) ? data.tasks : []))
          .catch(() => undefined),
        fetch(`${API_BASE}/api/upcoming-deadlines`)
          .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Failed to refresh deadlines"))))
          .then((data) => setDeadlines(Array.isArray(data.deadlines) ? data.deadlines : []))
          .catch(() => undefined),
        fetch(`${API_BASE}/api/notifications/pending`)
          .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Failed to refresh notifications"))))
          .then((data) => setPendingNotifications(Array.isArray(data.notifications) ? data.notifications : []))
          .catch(() => undefined),
      ]);
    } catch (err) {
      setError((err as Error).message || "Failed to add task");
    } finally {
      setAdding(false);
    }
  };

  const headlineDate = useMemo(() => formatLongDate(today), [today]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white flex relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-0 w-[700px] h-[700px] bg-gradient-to-tl from-purple-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
      </div>
      
      <aside className="w-64 bg-gradient-to-b from-slate-900/80 via-slate-800/80 to-slate-900/80 backdrop-blur-sm flex flex-col justify-between py-8 px-6 shadow-2xl border-r border-cyan-500/10 relative z-10">
        <div>
          <div className="mb-12">
            <h1 className="text-2xl font-black bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">TrackEneer</h1>
            <p className="text-xs text-slate-400 mt-1">Smart Task Scheduler</p>
          </div>
          <nav className="space-y-3">
            {[
              { label: "Study", icon: "📚",path:"/study" },
              { label: "Placcement", icon: "🎯",path:"/placement" },
              { label: "Insight", icon: "💡",path:"/insights" },
            ].map((item) => (
              <button key={item.label} className="w-full text-left px-4 py-3 rounded-lg text-slate-300 hover:bg-slate-700 hover:text-cyan-400 transition-all duration-200 font-medium text-sm">
                <span className="mr-2">{item.icon}</span>{item.label}
              </button>
            ))}
          </nav>
        </div>
        <button className="w-full px-4 py-3 rounded-lg text-slate-300 hover:bg-red-900/30 hover:text-red-400 transition-all duration-200 font-medium text-sm">🚪 Logout</button>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden bg-transparent">
        <header className="bg-slate-900/80 backdrop-blur-md border-b border-cyan-500/20 px-8 py-6 shadow-lg shadow-cyan-500/5">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h2 className="text-4xl font-black bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">Schedule</h2>
              <p className="text-slate-400 text-sm mt-1 font-medium">{headlineDate}</p>
              {quote && (
                <p className="mt-3 max-w-2xl italic text-slate-300 text-sm leading-relaxed">
                  <span className="text-cyan-400">✨</span> "{quote.content}"{quote.author ? ` — ${quote.author}` : ""}
                </p>
              )}
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-lg font-bold text-white">{session?.user?.name || 'User'}</p>
                <p className="text-xs text-slate-400 font-medium">{session?.user?.email || 'user@example.com'}</p>
              </div>
              <div className="relative">
                <Image
                  src={session?.user?.image || fallbackAvatar}
                  alt="Profile"
                  width={56}
                  height={56}
                  className="rounded-full border-2 border-cyan-400 shadow-lg shadow-cyan-500/20"
                />
                <div className="absolute bottom-0 right-0 w-3 h-3 bg-green-400 rounded-full border-2 border-slate-900"></div>
              </div>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-8 py-6">
          {error && (
            <div className="mb-6 rounded-lg bg-red-500/20 border border-red-500/40 px-4 py-3 text-sm text-red-400 shadow-sm">
              <span className="font-semibold">⚠️ Error:</span> {error}
            </div>
          )}

          <div className="grid gap-6 grid-cols-1 lg:grid-cols-3 mb-6">
            {/* Tasks Card */}
            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-cyan-500/20 hover:shadow-cyan-500/20 transition-all duration-300 group">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-extrabold text-white flex items-center">
                  <span className="mr-3 text-2xl">📋</span>Your Tasks
                </h3>
                <button
                  onClick={() => setOpenForm(true)}
                  className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-cyan-500 via-blue-500 to-blue-600 rounded-xl hover:shadow-xl hover:shadow-cyan-500/30 hover:scale-110 hover:-translate-y-0.5 transition-all duration-200 active:scale-95"
                >
                  + Add
                </button>
              </div>
              <ul className="space-y-3 text-sm max-h-96 overflow-y-auto pr-1 custom-scrollbar">
                {loading.tasks ? (
                  <li className="text-slate-400 py-4 text-center">⏳ Loading tasks…</li>
                ) : tasks.length === 0 ? (
                  <li className="text-slate-500 py-8 text-center text-sm">📭 No tasks scheduled for today.</li>
                ) : (
                  tasks.map((task) => (
                    <li key={task.id || task.title} className="rounded-xl bg-gradient-to-br from-slate-800/80 to-slate-700/80 p-4 border border-cyan-500/20 hover:border-cyan-400/60 hover:shadow-lg hover:shadow-cyan-500/10 transition-all duration-200 cursor-pointer group/item">
                      <p className="font-bold text-white text-base mb-1 group-hover/item:text-cyan-400 transition-colors">{task.title || "Untitled"}</p>
                      {task.description && <p className="text-xs text-slate-400 mt-1 line-clamp-2">{task.description}</p>}
                      <div className="mt-3 flex gap-4 text-xs text-slate-400 font-semibold">
                        {task.startTime && <span className="flex items-center gap-1"><span className="text-sm">🕐</span> {formatToIST(task.startTime)}</span>}
                        {task.endTime && <span className="flex items-center gap-1"><span className="text-sm">⏱️</span> {formatToIST(task.endTime)}</span>}
                      </div>
                    </li>
                  ))
                )}
              </ul>
            </div>

            {/* Recommendations Card */}
            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-blue-500/20 hover:shadow-blue-500/20 transition-all duration-300 group">
              <h3 className="text-xl font-extrabold text-white mb-4 flex items-center">
                <span className="mr-3 text-2xl">💡</span>Recommendations
              </h3>
              <p className="text-xs text-slate-400 mb-5 font-medium">Based on study & career data.</p>
              <div className="flex flex-wrap gap-2.5 max-h-96 overflow-y-auto custom-scrollbar">
                {loading.recs ? (
                  <p className="text-slate-400 text-sm py-4 w-full text-center">⏳ Loading…</p>
                ) : recommendations.length === 0 ? (
                  <p className="text-slate-500 text-sm py-8 w-full text-center">📭 No recommendations available.</p>
                ) : (
                  recommendations.map((rec, idx) => (
                    <button
                      key={rec.taskId ? `${rec.taskId}-${rec.label}` : `${rec.label}-${idx}`}
                      className="rounded-xl bg-gradient-to-r from-blue-500/20 via-cyan-500/20 to-blue-500/20 px-4 py-2.5 text-xs font-bold text-blue-300 border border-blue-500/40 hover:border-blue-400 hover:shadow-lg hover:shadow-blue-500/20 hover:scale-105 hover:-translate-y-0.5 transition-all duration-200 active:scale-95"
                      title={rec.type ? `${rec.type} • ${rec.estimate_minutes ?? 0} min` : undefined}
                    >
                      {rec.label}
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Deadlines Card */}
            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-purple-500/20 hover:shadow-purple-500/20 transition-all duration-300 group">
              <h3 className="text-xl font-extrabold text-white mb-6 flex items-center">
                <span className="mr-3 text-2xl">📅</span>Upcoming Deadlines
              </h3>
              <ul className="space-y-3 text-sm max-h-96 overflow-y-auto pr-1 custom-scrollbar">
                {loading.deadlines ? (
                  <li className="text-slate-400 py-4 text-center">⏳ Loading deadlines…</li>
                ) : deadlines.length === 0 ? (
                  <li className="text-slate-500 py-8 text-center text-sm">✅ No upcoming deadlines.</li>
                ) : (
                  deadlines.map((deadline) => (
                    <li key={`${deadline.title}-${deadline.dueDate}`} className="rounded-xl bg-gradient-to-br from-slate-800/80 to-slate-700/80 p-4 border border-purple-500/20 hover:border-purple-400/60 hover:shadow-lg hover:shadow-purple-500/10 transition-all duration-200 cursor-pointer group/item">
                      <p className="font-bold text-white text-base mb-2 group-hover/item:text-purple-400 transition-colors">{deadline.title || "Untitled"}</p>
                      <p className="text-xs text-slate-400 font-semibold flex items-center gap-1">
                        <span className="text-sm">📌</span> {formatDueDate(deadline.dueDate)}
                      </p>
                    </li>
                  ))
                )}
              </ul>
            </div>

            {/* Eisenhower Matrix Card */}
            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-yellow-500/20 hover:shadow-yellow-500/20 transition-all duration-300 group col-span-full lg:col-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-extrabold text-white flex items-center">
                  <span className="mr-3 text-2xl">🧭</span>Eisenhower Matrix
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { setShowEisenhowerModal(true); }}
                    className="px-3 py-1.5 text-xs font-bold text-white bg-yellow-500/20 border border-yellow-500/30 rounded-lg hover:bg-yellow-500/25 transition-all"
                  >View</button>
                </div>
              </div>
              <p className="text-xs text-slate-400 mb-4">Quick overview of prioritized tasks.</p>
              {loadingEisenhower ? (
                <p className="text-slate-400 text-sm">⏳ Loading…</p>
              ) : (!eisenhowerMatrix || !eisenhowerMatrix.matrix) ? (
                <p className="text-slate-500 text-sm">No matrix data available.</p>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(eisenhowerMatrix.matrix as any).map(([k, v]: [string, any]) => (
                    <div key={k} className="rounded-lg bg-slate-800/60 p-3 border border-yellow-500/10">
                      <p className="text-xs text-slate-300 font-semibold">{k}</p>
                      <p className="text-2xl font-black text-white mt-2">{v.count}</p>
                      <div className="mt-3 text-xs text-slate-400">
                        {v.tasks && v.tasks.length > 0 ? v.tasks.map((t: any) => (
                          <div key={t.id} className="mb-1">• {t.title}</div>
                        )) : <div className="text-slate-500">—</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Live Notifications & Pending Notifications */}
          <div className="grid gap-6 lg:grid-cols-2 mb-6">
            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-cyan-500/20 hover:shadow-cyan-500/20 transition-all duration-300 group">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-extrabold text-white flex items-center">
                  <span className="mr-3 text-2xl">🔔</span>Live Notifications
                </h3>
                <span className={`text-xs px-3 py-1.5 rounded-full font-bold shadow-sm ${wsStatus === "open" ? "bg-green-500/20 text-green-400 border border-green-500/40" : "bg-red-500/20 text-red-400 border border-red-500/40"}`}>
                  {wsStatus === "open" ? "🟢 Connected" : "🔴 Offline"}
                </span>
              </div>
              <ul className="space-y-3 text-sm max-h-72 overflow-y-auto pr-1 custom-scrollbar">
                {notifications.length === 0 ? (
                  <li className="text-slate-500 py-8 text-center">🌀 No live notifications yet.</li>
                ) : (
                  notifications.map((item) => (
                    <li key={item.id} className="rounded-xl bg-gradient-to-r from-slate-800/80 to-slate-700/80 p-4 border border-cyan-500/20 hover:border-cyan-400/60 hover:shadow-lg hover:shadow-cyan-500/10 transition-all duration-200 cursor-pointer group/item animate-fade-in">
                      <p className="font-bold text-white text-sm mb-2 group-hover/item:text-cyan-400 transition-colors">{item.label}</p>
                      <p className="text-xs text-slate-400 font-semibold flex items-center gap-1">
                        <span className="text-sm">🕐</span> {new Date(item.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </li>
                  ))
                )}
              </ul>
            </div>

            <div className="rounded-2xl bg-slate-900/80 backdrop-blur-sm p-6 shadow-2xl border border-purple-500/20 hover:shadow-purple-500/20 transition-all duration-300 group">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-extrabold text-white flex items-center">
                  <span className="mr-3 text-2xl">⏰</span>Next 15 Minutes
                </h3>
                <button
                  onClick={async () => {
                    setLoading((prev) => ({ ...prev, pending: true }));
                    try {
                      const response = await fetch(`${API_BASE}/api/notifications/pending`);
                      if (!response.ok) throw new Error("Failed to fetch notifications");
                      const data = await response.json();
                      setPendingNotifications(Array.isArray(data.notifications) ? data.notifications : []);
                      setNotifError(null);
                    } catch (err) {
                      setNotifError((err as Error).message || "Failed to fetch notifications");
                    } finally {
                      setLoading((prev) => ({ ...prev, pending: false }));
                    }
                  }}
                  className="px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-cyan-500 via-blue-500 to-blue-600 rounded-xl hover:shadow-xl hover:shadow-cyan-500/30 hover:scale-110 hover:-translate-y-0.5 transition-all duration-200 active:scale-95"
                >
                  🔄 Refresh
                </button>
              </div>
              {notifError && (
                <p className="mb-4 rounded-xl bg-red-500/20 border border-red-500/40 px-4 py-3 text-xs text-red-400 font-semibold shadow-sm">⚠️ {notifError}</p>
              )}
              <ul className="space-y-3 text-sm max-h-72 overflow-y-auto pr-1 custom-scrollbar">
                {loading.pending ? (
                  <li className="text-slate-400 py-4 text-center">⏳ Loading…</li>
                ) : pendingNotifications.length === 0 ? (
                  <li className="text-slate-500 py-8 text-center">✅ No upcoming notifications.</li>
                ) : (
                  pendingNotifications.map((item) => (
                    <li key={item.id} className="rounded-xl bg-gradient-to-br from-slate-800/80 to-slate-700/80 p-4 border border-purple-500/20 hover:border-purple-400/60 hover:shadow-lg hover:shadow-purple-500/10 transition-all duration-200 cursor-pointer group/item">
                      <p className="font-bold text-white text-sm mb-2 group-hover/item:text-purple-400 transition-colors">{item.title || "Task"}</p>
                      <p className="text-xs text-slate-400 font-semibold mb-1">
                        {item.type === "start" ? "⏱️ Starts in" : item.type === "due" ? "📌 Due" : "🔔 Scheduled"} {" "}
                        {typeof item.minutesUntil === "number" ? `${item.minutesUntil} min` : "soon"}
                      </p>
                      {(item.scheduledTime || item.dueTime) && (
                        <p className="text-xs text-slate-400 font-semibold flex items-center gap-1">
                          <span className="text-sm">🕐</span> {item.scheduledTime || item.dueTime}
                        </p>
                      )}
                    </li>
                  ))
                )}
              </ul>
            </div>
          </div>
        </div>

        {openForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
            <div className="w-full max-w-lg rounded-2xl bg-slate-900 p-8 shadow-2xl border border-cyan-500/30">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-2xl font-bold text-white">✏️ Add New Task</h3>
                <button onClick={() => setOpenForm(false)} className="text-slate-400 hover:text-slate-200 transition-colors font-bold text-xl">
                  ✕
                </button>
              </div>
              <form className="space-y-5" onSubmit={handleSubmit}>
                <div>
                  <label className="block text-sm font-bold text-slate-300 mb-2">Task Title</label>
                  <input
                    required
                    value={form.title}
                    onChange={handleChange("title")}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all"
                    placeholder="Enter task title"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-300 mb-2">Description</label>
                  <textarea
                    required
                    value={form.description}
                    onChange={handleChange("description")}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all resize-none"
                    rows={3}
                    placeholder="What is this task about?"
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="block text-sm font-bold text-slate-300 mb-2">Start Time</label>
                    <input
                      type="datetime-local"
                      required
                      value={form.startTime}
                      onChange={handleChange("startTime")}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-bold text-slate-300 mb-2">End Time</label>
                    <input
                      type="datetime-local"
                      required
                      value={form.endTime}
                      onChange={handleChange("endTime")}
                      className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-300 mb-2">Due Date <span className="text-xs text-slate-500 font-normal">(optional)</span></label>
                  <input
                    type="datetime-local"
                    value={form.dueDate}
                    onChange={handleChange("dueDate")}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-white focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 transition-all"
                  />
                </div>
                <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
                  <button
                    type="button"
                    onClick={() => {
                      resetForm();
                      setOpenForm(false);
                    }}
                    className="px-5 py-2.5 rounded-lg border border-slate-700 text-slate-300 font-bold hover:bg-slate-800 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-bold hover:shadow-lg hover:shadow-cyan-500/30 hover:scale-105 transition-all duration-200 disabled:opacity-50"
                    disabled={adding}
                  >
                    {adding ? "⏳ Saving…" : "✅ Save Task"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {showEisenhowerModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
            <div className="w-full max-w-4xl rounded-2xl bg-slate-900 p-6 shadow-2xl border border-yellow-500/30">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-2xl font-bold text-white">🧭 Eisenhower Matrix — Prioritized Tasks</h3>
                <button onClick={() => setShowEisenhowerModal(false)} className="text-slate-400 hover:text-slate-200 transition-colors font-bold text-xl">✕</button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {eisenhower && eisenhower.quadrants ? (
                  Object.entries(eisenhower.quadrants as any).map(([q, items]: [string, any]) => (
                    <div key={q} className="rounded-lg bg-slate-800/60 p-4 border border-yellow-500/10">
                      <h4 className="text-sm font-bold text-white mb-2">{q}</h4>
                      {items.length === 0 ? (
                        <p className="text-slate-500 text-sm">No tasks</p>
                      ) : (
                        <ul className="text-sm space-y-2 max-h-64 overflow-y-auto pr-2 custom-scrollbar">
                          {items.map((it: any) => (
                            <li key={it.id} className="p-2 rounded-md bg-slate-700/40 border border-slate-700">
                              <div className="flex justify-between items-start">
                                <div>
                                  <div className="font-semibold text-white">{it.title}</div>
                                  <div className="text-xs text-slate-400">{it.category || '—'} • {it.priority || '—'}</div>
                                  {it.deadline && <div className="text-xs text-slate-400 mt-1">Due: {new Date(it.deadline).toLocaleString()}</div>}
                                </div>
                                <div className="text-xs text-slate-300">{it.ai_scores ? `U:${(it.ai_scores.urgent||0).toFixed(2)} I:${(it.ai_scores.important||0).toFixed(2)}` : ''}</div>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400">No data available.</p>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default SchedulePage;
