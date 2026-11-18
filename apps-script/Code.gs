// Asset Arena Wire submission handler.
// Setup:
//   1. Create a Google Sheet named "Asset Arena Wire Submissions".
//   2. Extensions > Apps Script, paste ALL of this file, set SHEET_ID below.
//   3. Run setupSheet() once (authorize when asked) to write the header row.
//   4. Deploy > New deployment > Web app. Execute as: Me. Who has access: Anyone.
//   5. Copy the /exec URL into config.json "submit_endpoint", then rebuild.
// Publishing: select an approved row, then Asset Arena Wire > Publish selected
// row. It commits the release JSON and image to GitHub in one commit, the
// deploy workflow puts it live, and the row is marked Published with its URL.
// One time: Asset Arena Wire > Set GitHub token (see setGithubToken below).

var SHEET_ID = '1ult7sPwjQpgynWqjk26yEU_Flys8TmLpR5NsgKDOjGg';
var NOTIFY_EMAIL = 'lasday.david@gmail.com';

var HEADERS = [
  'Submitted', 'Status', 'Plan', 'Contact name', 'Email', 'Organization', 'Website',
  'Phone', 'Headline', 'Subheadline', 'Category', 'Dateline', 'Requested date',
  'Body', 'About', 'Media contact', 'Notes', 'Payment', 'Paid on', 'Published URL',
  'Image', 'Image caption'
];
var IMAGE_FOLDER_NAME = 'Asset Arena Wire Images';
var IMAGE_TYPES = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' };
var MAX_IMAGE_BYTES = 8 * 1024 * 1024;
// Status is the editorial decision; Payment is tracked separately.
var STATUS_VALUES = ['Pending', 'Approved', 'Rejected', 'Published'];
var PAYMENT_VALUES = ['Not invoiced', 'Invoiced', 'Paid', 'Waived'];

function doGet() {
  return ContentService.createTextOutput('Asset Arena Wire submission endpoint is live.');
}

function setupSheet() {
  formatSheet();
}

// Run once from the editor: keeps every row one line tall so long text
// (Body, About, Notes) is clipped instead of stretching rows. Click a cell to
// read its full text in the formula bar.
var COLUMN_WIDTHS = {
  'Submitted': 130, 'Status': 90, 'Plan': 120, 'Contact name': 130, 'Email': 180,
  'Organization': 150, 'Headline': 320, 'Category': 140, 'Body': 220, 'About': 160,
  'Notes': 160, 'Payment': 110, 'Paid on': 100, 'Published URL': 220, 'Image': 120
};
function formatSheet() {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  var rows = Math.max(sheet.getMaxRows() - 1, 1);
  var statusCol = HEADERS.indexOf('Status') + 1;
  var payCol = HEADERS.indexOf('Payment') + 1;

  // Older rows kept payment inside Status; move it to the Payment column.
  var last = sheet.getLastRow();
  if (last > 1) {
    var st = sheet.getRange(2, statusCol, last - 1, 1).getValues();
    var pay = sheet.getRange(2, payCol, last - 1, 1).getValues();
    for (var i = 0; i < st.length; i++) {
      if (st[i][0] === 'Invoiced' || st[i][0] === 'Paid') { pay[i][0] = st[i][0]; st[i][0] = 'Approved'; }
      if (PAYMENT_VALUES.indexOf(pay[i][0]) < 0) pay[i][0] = 'Not invoiced';
    }
    sheet.getRange(2, statusCol, last - 1, 1).setValues(st);
    sheet.getRange(2, payCol, last - 1, 1).setValues(pay);
  }

  var dropdown = function (values) {
    return SpreadsheetApp.newDataValidation().requireValueInList(values, true).setAllowInvalid(false).build();
  };
  var statusRange = sheet.getRange(2, statusCol, rows, 1);
  var payRange = sheet.getRange(2, payCol, rows, 1);
  statusRange.setDataValidation(dropdown(STATUS_VALUES));
  payRange.setDataValidation(dropdown(PAYMENT_VALUES));
  sheet.getRange(2, HEADERS.indexOf('Paid on') + 1, rows, 1).setNumberFormat('yyyy-mm-dd');

  var colors = {
    'Pending': '#fff2cc', 'Approved': '#d9ead3', 'Rejected': '#f4cccc', 'Published': '#cfe2f3',
    'Not invoiced': '#eeeeee', 'Invoiced': '#fff2cc', 'Paid': '#d9ead3', 'Waived': '#d9d2e9'
  };
  var managed = [statusRange.getA1Notation(), payRange.getA1Notation()];
  var rules = sheet.getConditionalFormatRules().filter(function (r) {
    return !r.getRanges().some(function (g) { return managed.indexOf(g.getA1Notation()) >= 0; });
  });
  STATUS_VALUES.forEach(function (v) {
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo(v).setBackground(colors[v]).setRanges([statusRange]).build());
  });
  PAYMENT_VALUES.forEach(function (v) {
    rules.push(SpreadsheetApp.newConditionalFormatRule().whenTextEqualTo(v).setBackground(colors[v]).setRanges([payRange]).build());
  });
  sheet.setConditionalFormatRules(rules);

  var all = sheet.getRange(1, 1, sheet.getMaxRows(), HEADERS.length);
  all.setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP).setVerticalAlignment('top');
  if (sheet.getMaxRows() > 1) sheet.setRowHeightsForced(2, sheet.getMaxRows() - 1, 21);
  Object.keys(COLUMN_WIDTHS).forEach(function (h) {
    var c = HEADERS.indexOf(h);
    if (c >= 0) sheet.setColumnWidth(c + 1, COLUMN_WIDTHS[h]);
  });
  sheet.setFrozenRows(1);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var p = (e && e.parameter) || {};
    if (p.company_url) return ContentService.createTextOutput('ok'); // honeypot

    var clean = function (v, max) {
      v = String(v || '').slice(0, max || 1000);
      return /^[=+\-@]/.test(v) ? "'" + v : v; // block formula injection
    };
    var row = [
      new Date(), 'Pending', clean(p.plan), clean(p.contact_name), clean(p.email),
      clean(p.organization), clean(p.website), clean(p.phone), clean(p.headline, 300),
      clean(p.subheadline, 400), clean(p.category), clean(p.dateline), clean(p.release_date),
      clean(p.body, 20000), clean(p.about, 3000), clean(p.media_contact), clean(p.notes, 3000),
      'Not invoiced', '', '', '', clean(p.image_caption, 300)
    ];
    // Save the image first; a bad image must not lose the submission.
    try {
      row[20] = saveImage_(p, clean(p.organization, 60));
    } catch (imgErr) {
      row[20] = p.image_data ? 'Image upload failed: ' + imgErr : '';
    }
    var sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
    sheet.appendRow(row);
    try {
      var last = sheet.getLastRow();
      sheet.getRange(last, 1, 1, HEADERS.length).setWrapStrategy(SpreadsheetApp.WrapStrategy.CLIP);
      sheet.setRowHeightsForced(last, 1, 21);
    } catch (fmtErr) { /* cosmetic only */ }

    try {
      MailApp.sendEmail({
        to: NOTIFY_EMAIL,
        subject: 'New Wire submission (' + row[2] + '): ' + row[8],
        body: [
          'Plan: ' + row[2],
          'From: ' + row[3] + ' <' + row[4] + '>',
          'Organization: ' + row[5] + ' ' + row[6],
          'Category: ' + row[10],
          'Requested date: ' + row[12],
          'Image: ' + (row[20] || 'none'),
          '',
          'Headline: ' + row[8],
          'Subheadline: ' + row[9],
          '',
          row[13],
          '',
          'Sheet: https://docs.google.com/spreadsheets/d/' + SHEET_ID + '/edit'
        ].join('\n'),
        replyTo: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(row[4]) ? row[4] : NOTIFY_EMAIL
      });
    } catch (mailErr) {
      // Row is saved already; a mail failure must not lose the submission.
    }
    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}

function imageFolder_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('IMAGE_FOLDER_ID');
  if (id) {
    try { return DriveApp.getFolderById(id); } catch (e) { /* folder deleted, recreate */ }
  }
  var folder = DriveApp.createFolder(IMAGE_FOLDER_NAME);
  props.setProperty('IMAGE_FOLDER_ID', folder.getId());
  return folder;
}

function saveImage_(p, org) {
  if (!p.image_data) return '';
  var type = String(p.image_type || '');
  var ext = IMAGE_TYPES[type];
  if (!ext) throw 'unsupported type ' + type;
  var bytes = Utilities.base64Decode(String(p.image_data));
  if (bytes.length > MAX_IMAGE_BYTES) throw 'file too large';
  var stamp = Utilities.formatDate(new Date(), 'UTC', 'yyyyMMdd-HHmmss');
  var name = stamp + '-' + (slugify_(org) || 'submission') + '.' + ext;
  var file = imageFolder_().createFile(Utilities.newBlob(bytes, type, name));
  return file.getUrl();
}

// Run once from the editor to create the image folder and grant Drive access.
function setupImages() {
  Logger.log(imageFolder_().getUrl());
}

// ---------- review and publishing

var GITHUB_REPO = 'Lasday40/asset-arena-wire';
var GITHUB_BRANCH = 'main';
var PUBLISHABLE = ['Approved', 'Published'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Asset Arena Wire')
    .addItem('Publish selected row', 'publishSelectedRow')
    .addItem('Preview release JSON for selected row', 'showReleaseJson')
    .addSeparator()
    .addItem('Set GitHub token', 'setGithubToken')
    .addToUi();
}

function slugify_(s) {
  return String(s).toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80).replace(/-$/, '');
}

function noDashes_(s) {
  // House style: no em or en dashes.
  return String(s || '').replace(/\s*[\u2013\u2014]\s*/g, ', ');
}

function unquote_(s) {
  s = String(s == null ? '' : s);
  return s.charAt(0) === "'" ? s.slice(1) : s;
}

function selectedRow_() {
  var sheet = SpreadsheetApp.getActiveSheet();
  var r = sheet.getActiveRange().getRow();
  if (r < 2) throw new Error('Select a submission row first.');
  var v = sheet.getRange(r, 1, 1, HEADERS.length).getValues()[0];
  return {
    sheet: sheet, row: r,
    get: function (name) { return v[HEADERS.indexOf(name)]; },
    set: function (name, value) { sheet.getRange(r, HEADERS.indexOf(name) + 1).setValue(value); }
  };
}

function driveId_(url) {
  var m = String(url || '').match(/\/d\/([\w-]{20,})/) || String(url || '').match(/[?&]id=([\w-]{20,})/);
  return m ? m[1] : '';
}

// Builds the release object from a Sheet row. slug and date can be forced
// (used when republishing an existing release).
function buildRelease_(row, opts) {
  opts = opts || {};
  var get = function (name) { return unquote_(row.get(name)); };
  var iso = opts.date || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  var media = get('Media contact');
  var emailMatch = media.match(/[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+/);
  var org = noDashes_(get('Organization')).trim();
  var release = {
    slug: opts.slug || slugify_(get('Headline')),
    status: 'published',
    date: iso,
    dateline: noDashes_(get('Dateline')).toUpperCase().trim(),
    category: get('Category').trim(),
    organization: { name: org, url: get('Website').trim() },
    founding_member: /founding/i.test(get('Plan')),
    headline: noDashes_(get('Headline')).trim(),
    subheadline: noDashes_(get('Subheadline')).trim(),
    body: noDashes_(get('Body')).split(/\n\s*\n/).map(function (s) { return s.replace(/\s*\n\s*/g, ' ').trim(); }).filter(String),
    about: get('About') ? [{ name: org, text: noDashes_(get('About')).trim() }] : [],
    contact: {
      name: noDashes_(emailMatch ? media.replace(emailMatch[0], '').replace(/[,;<>]+/g, ' ').replace(/\s+/g, ' ').trim() : get('Contact name')),
      organization: org,
      email: emailMatch ? emailMatch[0] : get('Email').trim()
    },
    tags: []
  };
  var image = null;
  var imageUrl = String(row.get('Image') || '');
  var fileId = /^https:/.test(imageUrl) ? driveId_(imageUrl) : '';
  if (fileId) {
    var blob = DriveApp.getFileById(fileId).getBlob();
    var ext = IMAGE_TYPES[blob.getContentType()] || 'jpg';
    var src = 'images/' + iso + '-' + release.slug + '.' + ext;
    release.image = { src: src, alt: release.headline, caption: noDashes_(get('Image caption')).trim() };
    image = { path: 'releases/' + src, blob: blob };
  }
  return { release: release, path: 'releases/' + iso + '-' + release.slug + '.json', image: image };
}

// Mirrors the checks in build.py so a bad row never breaks the live deploy.
function validateRelease_(r, categories) {
  var errors = [];
  ['slug', 'date', 'category', 'headline', 'dateline'].forEach(function (k) { if (!r[k]) errors.push('Missing ' + k); });
  if (!r.organization.name) errors.push('Missing organization');
  if (!r.body.length) errors.push('Missing release text (Body)');
  if (!r.contact.name && !r.contact.email) errors.push('Missing media contact');
  if (r.slug && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(r.slug)) errors.push('Headline gives a bad slug: ' + r.slug);
  if (r.category && categories.indexOf(r.category) < 0) errors.push('Category "' + r.category + '" is not one of: ' + categories.join(', '));
  if (/[\u2013\u2014]/.test(JSON.stringify(r))) errors.push('Contains an em or en dash');
  return errors;
}

// ---------- GitHub

function setGithubToken() {
  // Create a fine grained token at github.com/settings/personal-access-tokens:
  // Repository access: only Lasday40/asset-arena-wire. Permissions: Contents, Read and write.
  var ui = SpreadsheetApp.getUi();
  var res = ui.prompt('GitHub token', 'Paste a fine grained token with Contents: Read and write on ' + GITHUB_REPO + '.', ui.ButtonSet.OK_CANCEL);
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var token = res.getResponseText().trim();
  PropertiesService.getScriptProperties().setProperty('GITHUB_TOKEN', token);
  try {
    gh_('GET', '/repos/' + GITHUB_REPO);
    ui.alert('Token saved and working.');
  } catch (e) {
    ui.alert('Token saved, but GitHub rejected it: ' + e.message);
  }
}

// Run from the editor to authorize the script and test the token, which can
// also be set in Project Settings > Script properties as GITHUB_TOKEN.
function checkGithub() {
  var repo = gh_('GET', '/repos/' + GITHUB_REPO);
  if (!repo) throw new Error('GitHub token cannot see ' + GITHUB_REPO);
  Logger.log('GitHub token works for ' + repo.full_name + '. Can publish: ' + !!(repo.permissions && repo.permissions.push));
}

function gh_(method, path, body) {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) throw new Error('No GitHub token yet. Use Asset Arena Wire > Set GitHub token.');
  var opts = {
    method: method,
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' },
    muteHttpExceptions: true
  };
  if (body) { opts.contentType = 'application/json'; opts.payload = JSON.stringify(body); }
  var res = UrlFetchApp.fetch('https://api.github.com' + path, opts);
  var code = res.getResponseCode();
  if (code === 404 && method === 'GET') return null;
  if (code >= 300) throw new Error('GitHub ' + method + ' ' + path + ' failed (' + code + '): ' + res.getContentText().slice(0, 300));
  return JSON.parse(res.getContentText() || '{}');
}

function ghFile_(path) {
  var f = gh_('GET', '/repos/' + GITHUB_REPO + '/contents/' + path + '?ref=' + GITHUB_BRANCH);
  return f ? Utilities.newBlob(Utilities.base64Decode(f.content.replace(/\n/g, ''))).getDataAsString('UTF-8') : null;
}

// Writes several files in a single commit, so the site deploys once.
function ghCommit_(files, message) {
  var base = '/repos/' + GITHUB_REPO + '/git';
  var ref = gh_('GET', base + '/ref/heads/' + GITHUB_BRANCH);
  var head = gh_('GET', base + '/commits/' + ref.object.sha);
  var tree = files.map(function (f) {
    var blob = gh_('POST', base + '/blobs', { content: Utilities.base64Encode(f.bytes), encoding: 'base64' });
    return { path: f.path, mode: '100644', type: 'blob', sha: blob.sha };
  });
  var newTree = gh_('POST', base + '/trees', { base_tree: head.tree.sha, tree: tree });
  var commit = gh_('POST', base + '/commits', { message: message, tree: newTree.sha, parents: [head.sha] });
  gh_('PATCH', base + '/refs/heads/' + GITHUB_BRANCH, { sha: commit.sha });
  return commit;
}

// ---------- menu actions

function publishSelectedRow() {
  var ui = SpreadsheetApp.getUi();
  try {
    var row = selectedRow_();
    var status = String(row.get('Status'));
    if (PUBLISHABLE.indexOf(status) < 0) {
      ui.alert('Row ' + row.row + ' is "' + (status || 'blank') + '". Set Status to Approved first.');
      return;
    }
    var config = JSON.parse(ghFile_('config.json'));
    var base = config.base_url.replace(/\/$/, '');

    // Republishing keeps the original slug and date so the URL never changes.
    var existing = String(row.get('Published URL') || '').match(/\/news\/([a-z0-9-]+)\/?$/);
    var opts = {};
    var listing = gh_('GET', '/repos/' + GITHUB_REPO + '/contents/releases?ref=' + GITHUB_BRANCH) || [];
    if (existing) {
      var prior = listing.filter(function (f) { return f.name.slice(11) === existing[1] + '.json'; })[0];
      if (prior) opts = { slug: existing[1], date: prior.name.slice(0, 10) };
    }
    var built = buildRelease_(row, opts);
    var r = built.release;
    if (!existing) {
      var taken = function (slug) { return listing.some(function (f) { return f.name.slice(11) === slug + '.json'; }); };
      if (taken(r.slug)) {
        var alt = (r.slug + '-' + slugify_(r.organization.name)).slice(0, 90).replace(/-$/, '');
        for (var n = 2; taken(alt); n++) alt = r.slug + '-' + n;
        built = buildRelease_(row, { slug: alt });
        r = built.release;
      }
    }
    var errors = validateRelease_(r, config.categories);
    if (errors.length) { ui.alert('Not published. Fix these in the row first:\n\n' + errors.join('\n')); return; }

    var url = base + '/news/' + r.slug + '/';
    var notes = [];
    var payment = String(row.get('Payment') || 'Not invoiced');
    if (!existing && payment !== 'Paid' && payment !== 'Waived') notes.push('Payment is ' + payment + ', not Paid.');
    var requested = row.get('Requested date');
    if (requested && !existing) {
      var req = requested instanceof Date ? Utilities.formatDate(requested, Session.getScriptTimeZone(), 'yyyy-MM-dd') : String(requested);
      if (req !== r.date) notes.push('They requested ' + req + '. It will be dated ' + r.date + ' (today).');
    }
    var msg = (existing ? 'UPDATE the live release?' : 'Publish this release?') + '\n\n' +
      r.headline + '\n' + r.organization.name + ' | ' + r.category + ' | ' + r.date +
      (r.founding_member ? ' | Founding Member' : '') + '\n' +
      r.body.length + ' paragraphs' + (built.image ? ', with image' : ', no image') + '\n\n' +
      url + (notes.length ? '\n\n' + notes.join('\n') : '');
    if (ui.alert('Asset Arena Wire', msg, ui.ButtonSet.YES_NO) !== ui.Button.YES) return;

    var files = [{ path: built.path, bytes: Utilities.newBlob(JSON.stringify(r, null, 2) + '\n').getBytes() }];
    if (built.image) files.push({ path: built.image.path, bytes: built.image.blob.getBytes() });
    ghCommit_(files, (existing ? 'Update release: ' : 'Publish release: ') + r.headline);

    row.set('Status', 'Published');
    row.set('Published URL', url);
    ui.alert('Done. ' + (existing ? 'Updated' : 'Published') + ' to GitHub. The site rebuilds in about 2 minutes:\n\n' + url);
  } catch (e) {
    ui.alert('Publish failed, nothing was marked Published.\n\n' + e.message);
  }
}

function showReleaseJson() {
  try {
    var built = buildRelease_(selectedRow_());
    var json = JSON.stringify(built.release, null, 2);
    var out = HtmlService.createHtmlOutput(
      '<p style="font-family:sans-serif">Preview of <b>' + built.path + '</b>' +
      (built.image ? ' plus <b>' + built.image.path + '</b>' : '') + '</p>' +
      '<textarea style="width:100%;height:420px;font-family:monospace">' +
      json.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea>'
    ).setWidth(720).setHeight(520);
    SpreadsheetApp.getUi().showModalDialog(out, 'Release JSON');
  } catch (e) {
    SpreadsheetApp.getUi().alert(e.message);
  }
}
