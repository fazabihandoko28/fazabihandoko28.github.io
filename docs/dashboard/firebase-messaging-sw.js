/* HANZ Firebase Messaging Service Worker
   Scope: /dashboard/
   File: docs/dashboard/firebase-messaging-sw.js
*/

/*
  Register notificationclick BEFORE importing Firebase Messaging.
*/
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const targetUrl = new URL(
    event.notification?.data?.url || "/dashboard/swing/",
    self.registration.scope
  ).href;

  event.waitUntil(
    clients
      .matchAll({
        type: "window",
        includeUncontrolled: true
      })
      .then((clientList) => {
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
    "[HANZ SW] Background FCM message received:",
    payload
  );

  /*
    Notification messages sent by Firebase Console
    are normally displayed automatically by FCM
    when the web app is in the background.

    HANZ backend data-only messages are displayed
    manually below.
  */
  if (payload?.notification) {
    console.log(
      "[HANZ SW] Notification payload detected; FCM handles display."
    );
    return;
  }

  const data = payload?.data || {};

  const title =
    data.title ||
    "HANZ Swing Alert";

  const options = {
    body:
      data.body ||
      data.message ||
      "New HANZ trading alert.",

    tag:
      data.dedupe_key ||
      data.alert_id ||
      undefined,

    renotify: false,

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
