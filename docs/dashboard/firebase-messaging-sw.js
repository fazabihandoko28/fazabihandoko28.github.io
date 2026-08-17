/* HANZ Firebase Messaging Service Worker
   Force-show background notifications for both:
   - notification payloads
   - data-only payloads
*/

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const targetUrl = new URL(
    event.notification?.data?.url || "/dashboard/swing/",
    self.registration.scope
  ).href;

  event.waitUntil(
    clients.matchAll({
      type: "window",
      includeUncontrolled: true
    }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          try {
            client.navigate(targetUrl);
          } catch (_) {}

          return client.focus();
        }
      }

      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});

importScripts(
  "https://www.gstatic.com/firebasejs/12.17.1/firebase-app-compat.js"
);

importScripts(
  "https://www.gstatic.com/firebasejs/12.17.1/firebase-messaging-compat.js"
);

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
  console.log(
    "[HANZ SW] Background message received:",
    payload
  );

  const notification =
    payload?.notification || {};

  const data =
    payload?.data || {};

  const title =
    notification.title ||
    data.title ||
    "HANZ Swing Alert";

  const options = {
    body:
      notification.body ||
      data.body ||
      data.message ||
      "New HANZ trading alert.",

    tag:
      notification.tag ||
      data.dedupe_key ||
      data.alert_id ||
      "hanz-swing-alert",

    renotify: true,

    data: {
      url:
        data.url ||
        "/dashboard/swing/",

      ticker:
        data.ticker ||
        null,

      alert_type:
        data.alert_type ||
        null
    }
  };

  return self.registration.showNotification(
    title,
    options
  );
});
