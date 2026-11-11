// Asset Arena Wire submission handler.
// Setup:
//   1. Create a Google Sheet named "Asset Arena Wire Submissions".
//   2. Extensions > Apps Script, paste ALL of this file, set SHEET_ID below.
//   3. Run setupSheet() once (authorize when asked) to write the header row.
//   4. Deploy > New deployment > Web app. Execute as: Me. Who has access: Anyone.
//   5. Copy the /exec URL into config.json "submit_endpoint", then rebuild.
// Reviewing: select a row, then use the "Asset Arena Wire" menu to generate
// the release JSON for the releases/ folder.

var SHEET_ID = 'PASTE_SHEET_ID_HERE';
var NOTIFY_EMAIL = 'lasday.david@gmail.com';

var HEADERS = [
  'Submitted', 'Status', 'Plan', 'Contact name', 'Email', 'Organization', 'Website',
  'Phone', 'Headline', 'Subheadline', 'Category', 'Dateline', 'Requested date',
  'Body', 'About', 'Media contact', 'Notes', 'Invoice sent', 'Paid', 'Published URL'
];

function doGet() {
  return ContentService.createTextOutput('Asset Arena Wire submission endpoint is live.');
}

function setupSheet() {
  var sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  var statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['Pending', 'Approved', 'Rejected', 'Invoiced', 'Paid', 'Published'], true).build();
  sheet.getRange(2, 2, 1000, 1).setDataValidation(statusRule);
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
      '', '', ''
    ];
    var sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
    sheet.appendRow(row);

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

// ---------- review helpers

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Asset Arena Wire')
    .addItem('Generate release JSON for selected row', 'showReleaseJson')
    .addToUi();
}

function slugify_(s) {
  return String(s).toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80);
}

function noDashes_(s) {
  // House style: no em or en dashes.
  return String(s || '').replace(/\s*[\u2013\u2014]\s*/g, ', ');
}

function showReleaseJson() {
  var sheet = SpreadsheetApp.getActiveSheet();
  var r = sheet.getActiveRange().getRow();
  if (r < 2) { SpreadsheetApp.getUi().alert('Select a submission row first.'); return; }
  var v = sheet.getRange(r, 1, 1, HEADERS.length).getValues()[0];
  var get = function (name) { return v[HEADERS.indexOf(name)]; };
  var unquote = function (s) { s = String(s || ''); return s.charAt(0) === "'" ? s.slice(1) : s; };

  var d = get('Requested date');
  var iso = d instanceof Date ? Utilities.formatDate(d, 'UTC', 'yyyy-MM-dd')
    : (String(d).match(/^\d{4}-\d{2}-\d{2}$/) ? String(d) : Utilities.formatDate(new Date(), 'UTC', 'yyyy-MM-dd'));
  var media = unquote(get('Media contact'));
  var emailMatch = media.match(/[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+/);
  var org = unquote(get('Organization'));
  var release = {
    slug: slugify_(unquote(get('Headline'))),
    status: 'published',
    date: iso,
    dateline: unquote(get('Dateline')).toUpperCase(),
    category: unquote(get('Category')),
    organization: { name: org, url: unquote(get('Website')) },
    founding_member: /founding/i.test(get('Plan')),
    headline: noDashes_(unquote(get('Headline'))),
    subheadline: noDashes_(unquote(get('Subheadline'))),
    body: noDashes_(unquote(get('Body'))).split(/\n\s*\n/).map(function (s) { return s.replace(/\s*\n\s*/g, ' ').trim(); }).filter(String),
    about: unquote(get('About')) ? [{ name: org, text: noDashes_(unquote(get('About'))) }] : [],
    contact: {
      name: emailMatch ? media.replace(emailMatch[0], '').replace(/[,;]+/g, ' ').trim() : unquote(get('Contact name')),
      organization: org,
      email: emailMatch ? emailMatch[0] : unquote(get('Email'))
    },
    tags: []
  };
  var filename = iso + '-' + release.slug + '.json';
  var json = JSON.stringify(release, null, 2);
  var out = HtmlService.createHtmlOutput(
    '<p style="font-family:sans-serif">Save as <b>releases/' + filename + '</b></p>' +
    '<textarea style="width:100%;height:420px;font-family:monospace">' +
    json.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</textarea>'
  ).setWidth(720).setHeight(520);
  SpreadsheetApp.getUi().showModalDialog(out, 'Release JSON');
}
