/*
 * Reads ?t=<seconds> and seeks the lesson's Vimeo player there.
 * iOS Safari can silently ignore setCurrentTime before playback starts, so on
 * iOS (or whenever the seek doesn't stick) we show a "Ir al minuto" button:
 * a tap is a user gesture, which lets the player seek and play.
 */
(function () {
  'use strict';

  var t = parseInt(new URLSearchParams(window.location.search).get('t'), 10);
  if (!(t >= 0) || !window.Vimeo) return;

  var iframe = document.querySelector('iframe[src*="player.vimeo.com/video/"]');
  if (!iframe) return;

  var player = new window.Vimeo.Player(iframe);
  var isIOS = /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

  function label(sec) {
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    var mm = h ? String(m).padStart(2, '0') : String(m);
    return (h ? h + ':' : '') + mm + ':' + String(s).padStart(2, '0');
  }

  function showButton() {
    if (document.querySelector('.socio-seek-button')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'socio-seek-button';
    btn.textContent = 'Ir al minuto ' + label(t);
    btn.addEventListener('click', function () {
      player.play()
        .then(function () { return player.setCurrentTime(t); })
        .catch(function () { return player.setCurrentTime(t); })
        .then(function () { btn.remove(); })
        .catch(function () {});
    });
    iframe.parentNode.insertBefore(btn, iframe.nextSibling);
  }

  function verify() {
    // Silent-failure check: did the seek actually land near t?
    setTimeout(function () {
      player.getCurrentTime().then(function (now) {
        if (Math.abs(now - t) > 3) showButton();
      }).catch(showButton);
    }, 1500);
  }

  player.ready().then(function () {
    if (isIOS) { showButton(); return; }
    player.setCurrentTime(t).then(verify).catch(showButton);
    iframe.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }).catch(showButton);
})();
