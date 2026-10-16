export const createFirstUseBootstrapScript = ({
  storageKey,
  version,
  countdownMilliseconds = 20_000,
} = {}) => {
  const serializedStorageKey = JSON.stringify(String(storageKey || 'ui.first_use_agreement'))
  const serializedVersion = JSON.stringify(String(version || ''))
  const serializedCountdown = JSON.stringify(Math.max(0, Number(countdownMilliseconds) || 0))

  return `;(function () {
  'use strict';

  var storageKey = ${serializedStorageKey};
  var agreementVersion = ${serializedVersion};
  var countdownMilliseconds = ${serializedCountdown};
  var pathname = String(window.location.pathname || '/');
  var isAgreementRoute = /^\\/agreement\\/?$/.test(pathname);

  function readAcceptance() {
    try {
      var stored = JSON.parse(window.localStorage.getItem(storageKey) || 'null');
      return !!stored && stored.version === agreementVersion && !!stored.acceptedAt;
    } catch (_error) {
      return false;
    }
  }

  function currentRedirect() {
    return String(window.location.pathname || '/')
      + String(window.location.search || '')
      + String(window.location.hash || '');
  }

  function normalizeRedirect(value) {
    var target = String(value || '').trim();
    if (target.indexOf('/') !== 0 || target.indexOf('//') === 0 || target.indexOf('/agreement') === 0) {
      return '/';
    }
    return target;
  }

  if (!isAgreementRoute) {
    document.documentElement.removeAttribute('data-first-use-route');
    if (!readAcceptance()) {
      var agreementUrl = '/agreement?redirect=' + encodeURIComponent(currentRedirect());
      window.location.replace(agreementUrl);
      return;
    }
    document.documentElement.setAttribute('data-first-use-accepted', 'true');
    return;
  }

  document.documentElement.removeAttribute('data-first-use-accepted');
  document.documentElement.setAttribute('data-first-use-route', 'agreement');
  var countdownStartedAt = Date.now();

  function installAgreementFallback() {
    var page = document.querySelector('.first-use-page');
    if (!page || page.getAttribute('data-first-use-mounted') === 'true') return;

    var routeGuard = document.querySelector('.first-use-route-guard');
    if (routeGuard) routeGuard.hidden = true;

    var button = document.querySelector('[data-testid="first-use-confirm"]');
    if (!button) return;

    var buttonLabel = button.querySelector('span');
    var statusCopy = document.querySelector('.first-use-footer-status p');
    var statusDot = document.querySelector('.first-use-status-dot');
    var intervalId = null;

    function stopFallback() {
      if (intervalId !== null) window.clearInterval(intervalId);
      intervalId = null;
    }

    function updateFallback() {
      if (page.getAttribute('data-first-use-mounted') === 'true') {
        stopFallback();
        return;
      }

      var remaining = Math.max(0, countdownMilliseconds - (Date.now() - countdownStartedAt));
      var remainingSeconds = Math.ceil(remaining / 1000);
      if (remaining <= 0) {
        button.disabled = false;
        if (buttonLabel) buttonLabel.textContent = '我已阅读全部内容并同意';
        if (statusCopy) statusCopy.textContent = '重点和边界都看完了，确认后开工。';
        if (statusDot) statusDot.classList.add('ready');
        stopFallback();
        return;
      }

      button.disabled = true;
      if (buttonLabel) buttonLabel.textContent = '请阅读（' + remainingSeconds + ' 秒）';
      if (statusCopy) statusCopy.textContent = '请先读完关键内容，' + remainingSeconds + ' 秒后可确认。';
    }

    button.addEventListener('click', function (event) {
      if (page.getAttribute('data-first-use-mounted') === 'true') return;
      if (button.disabled || Date.now() - countdownStartedAt < countdownMilliseconds) {
        event.preventDefault();
        return;
      }

      try {
        window.localStorage.setItem(storageKey, JSON.stringify({
          version: agreementVersion,
          acceptedAt: new Date().toISOString()
        }));
      } catch (_error) {}

      var redirect = '/';
      try {
        redirect = normalizeRedirect(new URL(window.location.href).searchParams.get('redirect'));
      } catch (_error) {}
      document.documentElement.removeAttribute('data-first-use-route');
      document.documentElement.setAttribute('data-first-use-accepted', 'true');
      window.location.replace(redirect);
    });

    updateFallback();
    if (button.disabled) intervalId = window.setInterval(updateFallback, 200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      window.setTimeout(installAgreementFallback, 1200);
    }, { once: true });
  } else {
    window.setTimeout(installAgreementFallback, 1200);
  }
})();`
}
