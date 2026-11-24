const cacheName = "llegar-al-fresco-shell-v10";
self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(cacheName);
      const html = await fetch("/", { cache: "reload" });
      if (!html.ok)
        throw new Error("No se pudo preparar la aplicación sin conexión.");
      const assets = [
        ...(await html.clone().text()).matchAll(
          /(?:src|href)="(\/assets\/[^"]+)"/g,
        ),
      ].map((match) => match[1]);
      await cache.addAll([
        "/manifest.webmanifest",
        "/icon-192.png",
        "/icon-512.png",
        "/fonts/atkinson-hyperlegible-next-latin.woff2",
        "/fonts/source-serif-4-latin.woff2",
        ...assets,
      ]);
      await cache.put("/", html);
      await self.skipWaiting();
    })(),
  );
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter(
            (key) => key.startsWith("llegar-al-fresco-") && key !== cacheName,
          )
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (
    request.method !== "GET" ||
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/api/")
  )
    return;
  event.respondWith(
    fetch(request)
      .then(async (response) => {
        if (response.ok)
          await (await caches.open(cacheName))
            .put(request, response.clone())
            .catch(() => {});
        return response;
      })
      .catch(
        async () =>
          (await caches.match(request)) ||
          (request.mode === "navigate" ? await caches.match("/") : undefined) ||
          Response.error(),
      ),
  );
});
