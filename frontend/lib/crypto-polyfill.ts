/** Runs in <head> before React bundles — fixes HTTP VMs where crypto.randomUUID is missing. */
export const CRYPTO_RANDOM_UUID_POLYFILL = `
(function () {
  var root = typeof globalThis !== "undefined" ? globalThis : window;
  if (!root.crypto) {
    root.crypto = {};
  }
  if (typeof root.crypto.randomUUID !== "function") {
    root.crypto.randomUUID = function () {
      return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        var v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    };
  }
})();
`;
