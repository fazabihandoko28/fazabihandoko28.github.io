importScripts("https://www.gstatic.com/firebasejs/12.17.1/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.17.1/firebase-messaging-compat.js");

firebase.initializeApp({
  apiKey: "AIzaSyAqNOI43fKCFSsJFmSM1VDu1QHYOfBQ5yw",
  authDomain: "hanz-trading-intelligenc-c8f4d.firebaseapp.com",
  projectId: "hanz-trading-intelligenc-c8f4d",
  storageBucket: "hanz-trading-intelligenc-c8f4d.firebasestorage.app",
  messagingSenderId: "313426947063",
  appId: "1:313426947063:web:39450e958b473d8e089cf2"
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const data = payload?.data || {};
  const notification = payload?.notification || {};
  const title = data.title || notification.title || "HANZ Alert";
  const body = data.body || data.message || notification.body || "New HANZ trading alert.";

  return self.registration.showNotification(title, {
    body,
    tag: data.dedupe_key || data.alert_id || undefined,
    data: {
      url: data.url || "/dashboard/swing/",
      ticker: data.ticker || null,
      alert_type: data.alert_type || null
    }
  });
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = event.notification?.data?.url || "/dashboard/swing/";

  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if ("focus" in client) {
        if ("navigate" in client) {
          try { await client.navigate(targetUrl); } catch (_) {}
        }
        return client.focus();
      }
    }
    if (clients.openWindow) return clients.openWindow(targetUrl);
  })());
});
