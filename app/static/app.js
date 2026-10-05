(function () {
  'use strict';
  var app = angular.module('fnv', ['ngRoute']);

  app.config(['$routeProvider', '$locationProvider', function ($r, $l) {
    $l.hashPrefix('!');
    $r.when('/', { templateUrl: 'views/check.html', controller: 'CheckCtrl' })
      .when('/result/:id', { templateUrl: 'views/result.html', controller: 'ResultCtrl' })
      .when('/history', { templateUrl: 'views/history.html', controller: 'HistoryCtrl' })
      .when('/trending', { templateUrl: 'views/trending.html', controller: 'TrendingCtrl' })
      .when('/admin', { templateUrl: 'views/admin.html', controller: 'AdminCtrl' })
      .otherwise({ redirectTo: '/' });
  }]);

  app.filter('urlenc', function () { return function (v) { return encodeURIComponent(v || ''); }; });

  // Holds the latest result in memory so un-saved checks (no share link) can still be shown.
  app.value('Last', { r: null });

  app.factory('Api', ['$http', function ($http) {
    var cid = null;
    try {
      cid = localStorage.getItem('fnv_client');
      if (!cid) { cid = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem('fnv_client', cid); }
    } catch (e) { cid = 'anon'; }
    var cfg = { headers: { 'X-Client-Id': cid } };
    function adminCfg(key) { return { headers: { 'X-Admin-Key': key } }; }
    return {
      check: function (p) { return $http.post('/api/check', p, cfg); },
      recheck: function (id) { return $http.post('/api/checks/' + encodeURIComponent(id) + '/recheck', {}, cfg); },
      get: function (id) { return $http.get('/api/checks/' + encodeURIComponent(id)); },
      history: function () { return $http.get('/api/checks', cfg); },
      card: function (id, lang) { return $http.get('/api/checks/' + encodeURIComponent(id) + '/card', { params: { lang: lang } }); },
      flag: function (id, p) { return $http.post('/api/checks/' + encodeURIComponent(id) + '/flag', p); },
      trending: function () { return $http.get('/api/trending'); },
      adminQueue: function (k) { return $http.get('/api/admin/queue', adminCfg(k)); },
      adminStats: function (k) { return $http.get('/api/admin/stats', adminCfg(k)); },
      adminReview: function (k, id, p) { return $http.post('/api/admin/review/' + encodeURIComponent(id), p, adminCfg(k)); }
    };
  }]);

  function errText(e) {
    var d = e && e.data && e.data.detail;
    if (typeof d === 'string') { return d; }
    if (Array.isArray(d) && d[0]) { return d[0].msg || 'Invalid input.'; }
    return 'Something went wrong. Please try again.';
  }
  function cls(v) { return 'v-' + String(v).toLowerCase().replace(/\s+/g, '-'); }
  function pct(c) { return Math.round((c || 0) * 100); }

  app.controller('CheckCtrl', ['$scope', '$location', '$interval', 'Api', 'Last', function ($s, $loc, $interval, Api, Last) {
    var steps = ['Reading your input', 'Extracting claims', 'Searching fact-checks and news', 'Weighing the evidence', 'Verifying every citation'];
    $s.mode = 'text'; $s.f = { text: '', url: '', save: true }; $s.busy = false; $s.error = ''; $s.step = steps[0];
    var shared = $loc.search().shared;
    if (shared) {
      if (/^https?:\/\/\S+$/.test(shared.trim())) { $s.mode = 'url'; $s.f.url = shared.trim(); } else { $s.f.text = shared; }
    }
    var timer;
    $s.setMode = function (m) { $s.mode = m; $s.error = ''; };
    $s.submit = function () {
      $s.error = '';
      var payload = $s.mode === 'url' ? { url: $s.f.url } : { text: $s.f.text };
      if (!(payload.url || payload.text || '').trim()) { $s.error = 'Enter a claim or a link first.'; return; }
      payload.save = $s.f.save;
      var i = 0; $s.busy = true; $s.step = steps[0];
      timer = $interval(function () { i = Math.min(i + 1, steps.length - 1); $s.step = steps[i]; }, 4000);
      Api.check(payload).then(function (r) { Last.r = r.data; $loc.search({}).path('/result/' + r.data.id); })
        .catch(function (e) { $s.error = errText(e); })
        .finally(function () { $s.busy = false; $interval.cancel(timer); });
    };
    $s.$on('$destroy', function () { $interval.cancel(timer); });
  }]);

  app.controller('ResultCtrl', ['$scope', '$routeParams', '$location', 'Api', 'Last', function ($s, $p, $loc, Api, Last) {
    var LABELS = { supports: 'Supports the claim', refutes: 'Contradicts the claim', neutral: 'Related, no clear stance' };
    $s.loading = true; $s.r = null; $s.error = '';
    $s.ui = { lang: 'en', card: '' }; $s.cardError = ''; $s.flag = { reason: 'wrong_verdict', note: '', sent: false, error: '' };
    $s.pct = pct; $s.cls = cls;

    function prepare(r) {
      (r.claims || []).forEach(function (c) {
        var cited = {}; (c.citations || []).forEach(function (id) { cited[id] = true; });
        var buckets = { supports: [], refutes: [], neutral: [] };
        Object.keys(c.stances || {}).forEach(function (id) {
          if (r.evidence[id] && (c.stances[id] !== 'neutral' || cited[id])) { buckets[c.stances[id]].push(r.evidence[id]); }
        });
        (c.citations || []).forEach(function (id) {
          var s = (c.stances || {})[id];
          if (!s && r.evidence[id]) { buckets.neutral.push(r.evidence[id]); }
        });
        c.groups = ['supports', 'refutes', 'neutral'].filter(function (k) { return buckets[k].length; })
          .map(function (k) { return { key: k, label: LABELS[k], items: buckets[k] }; });
      });
      return r;
    }
    function done(r) { $s.r = prepare(r); $s.link = location.origin + '/#!/result/' + r.id; }

    if (Last.r && Last.r.id === $p.id) { done(Last.r); $s.loading = false; }
    else {
      Api.get($p.id).then(function (res) { done(res.data); })
        .catch(function () { $s.error = 'We could not find that result.'; })
        .finally(function () { $s.loading = false; });
    }
    $s.decided = function (v) { return v === 'True' || v === 'False' || v === 'Misleading'; };

    $s.loadCard = function () {
      $s.cardError = ''; $s.ui.card = ''; $s.copied = false;
      Api.card($p.id, $s.ui.lang).then(function (res) { $s.ui.card = res.data.text; }).catch(function () { $s.cardError = 'Share text is only available for saved checks.'; });
    };
    $s.copyCard = function () { if (navigator.clipboard && $s.ui.card) { navigator.clipboard.writeText($s.ui.card); $s.copied = true; } };
    $s.copyLink = function () { if (navigator.clipboard) { navigator.clipboard.writeText($s.link); $s.copiedLink = true; } };
    $s.sendFlag = function () {
      $s.flag.error = '';
      Api.flag($p.id, { reason: $s.flag.reason, note: $s.flag.note }).then(function () { $s.flag.sent = true; })
        .catch(function (e) { $s.flag.error = errText(e); });
    };
    $s.recheck = function () {
      $s.rechecking = true;
      Api.recheck($p.id).then(function (res) { Last.r = res.data; $loc.path('/result/' + res.data.id); })
        .catch(function (e) { $s.error = errText(e); })
        .finally(function () { $s.rechecking = false; });
    };
  }]);

  app.controller('HistoryCtrl', ['$scope', 'Api', function ($s, Api) {
    $s.loading = true; $s.items = []; $s.cls = cls;
    Api.history().then(function (r) { $s.items = r.data; }).finally(function () { $s.loading = false; });
  }]);

  app.controller('TrendingCtrl', ['$scope', 'Api', function ($s, Api) {
    $s.loading = true; $s.items = []; $s.cls = cls;
    Api.trending().then(function (r) { $s.items = r.data; }).finally(function () { $s.loading = false; });
  }]);

  app.controller('AdminCtrl', ['$scope', 'Api', function ($s, Api) {
    $s.key = ''; try { $s.key = sessionStorage.getItem('fnv_admin') || ''; } catch (e) {}
    $s.items = []; $s.stats = null; $s.error = ''; $s.cls = cls; $s.pct = pct;
    $s.load = function () {
      $s.error = '';
      try { sessionStorage.setItem('fnv_admin', $s.key); } catch (e) {}
      Api.adminQueue($s.key).then(function (r) { $s.items = r.data; })
        .catch(function (e) { $s.error = errText(e); $s.items = []; });
      Api.adminStats($s.key).then(function (r) { $s.stats = r.data; }).catch(function () { $s.stats = null; });
    };
    $s.review = function (it, verdict) {
      Api.adminReview($s.key, it.id, { verdict: verdict, note: it.reviewNote || '' }).then(function () {
        $s.items = $s.items.filter(function (x) { return x.id !== it.id; });
      }).catch(function (e) { $s.error = errText(e); });
    };
    if ($s.key) { $s.load(); }
  }]);
})();
