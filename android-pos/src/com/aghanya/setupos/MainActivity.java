package com.aghanya.setupos;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

// Setu POS on the phone: the restaurant's Setu from the counter PC (restaurant WiFi) or from Hotel Setu Cloud.
// The first screen (assets/start.html) picks one; the choice is remembered. SA bridge: save / share files, print, copy.
public class MainActivity extends Activity {
    static final String CLOUD = "https://setu-cloud.theinkthreadhub.workers.dev/hotel_erp.html";
    static final String START = "file:///android_asset/start.html";
    WebView web;
    SharedPreferences prefs;
    ValueCallback<Uri[]> pick;
    static final int PICK = 7;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("setu", Context.MODE_PRIVATE);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0f172a"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // login token, error log, remembered choices
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportMultipleWindows(false);
        s.setUserAgentString(s.getUserAgentString() + " SetuPOSApp/1.0");
        web.addJavascriptInterface(new Bridge(), "SA");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return openOutside(r.getUrl()); }
            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) { return openOutside(Uri.parse(url)); }
            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) showOffline();
            }
            @SuppressWarnings("deprecation")
            @Override
            public void onReceivedError(WebView v, int code, String desc, String url) {
                if (url != null && url.equals(v.getUrl())) showOffline();
            }
        });
        // alert / confirm / prompt dialogs and the file picker (Restore from backup, Excel import)
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (pick != null) pick.onReceiveValue(null);
                pick = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try { startActivityForResult(Intent.createChooser(i, "Choose file"), PICK); }
                catch (Exception e) { pick = null; return false; }
                return true;
            }
        });
        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(prefs.getString("url", "").isEmpty() ? START : prefs.getString("url", ""));
    }

    String host() {
        try { return Uri.parse(prefs.getString("url", "")).getHost(); } catch (Exception e) { return ""; }
    }

    // Setu itself stays inside the app; WhatsApp, calls, UPI and other sites open in their own apps
    boolean openOutside(Uri u) {
        String scheme = u.getScheme() == null ? "" : u.getScheme();
        if (scheme.equals("file")) return false;
        if ((scheme.equals("https") || scheme.equals("http")) && u.getHost() != null && u.getHost().equals(host())) return false;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { }
        return true;
    }

    void showOffline() {
        String url = prefs.getString("url", "");
        boolean lan = url.startsWith("http://");
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
            + "<body style='font-family:sans-serif;background:#0f172a;color:#e2e8f0;text-align:center;padding:60px 24px'>"
            + "<h2 style='color:#fff'>Setu se jud nahi paye</h2><p>" + (lan
                ? "Counter PC chalu hai? Ye phone usi restaurant WiFi par hai? Counter PC par Setu khula hona chahiye."
                : "Internet check karein.") + "</p>"
            + "<button onclick=\"location.href='" + url + "'\" style='background:#2563eb;color:#fff;border:0;border-radius:10px;padding:14px 28px;font-size:16px;margin:8px'>Dobara koshish</button><br>"
            + "<button onclick='SA.change()' style='background:transparent;color:#e2e8f0;border:1px solid #475569;border-radius:10px;padding:12px 24px;font-size:15px;margin:8px'>Connection badlo</button>"
            + "<p style='margin-top:40px;color:#94a3b8;font-size:13px'>Setu POS &middot; Aghanya Devanya Enterprises</p></body></html>";
        web.loadDataWithBaseURL(START, html, "text/html", "utf-8", null);
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == PICK && pick != null) {
            pick.onReceiveValue(res == RESULT_OK && data != null && data.getData() != null ? new Uri[]{ data.getData() } : null);
            pick = null;
            return;
        }
        super.onActivityResult(req, res, data);
    }

    // Back inside Setu goes back; at Setu's first page it shows the choice screen; there it closes the app
    @Override
    public void onBackPressed() {
        if (START.equals(web.getUrl())) super.onBackPressed();
        else if (web.canGoBack()) web.goBack();
        else web.loadUrl(START);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() { super.onResume(); web.onResume(); }

    @Override
    protected void onPause() { web.onPause(); super.onPause(); }

    class Bridge {
        // start.html: remember where Setu runs and open it
        @JavascriptInterface
        public void open(final String where, final String ip) {
            runOnUiThread(new Runnable() { @Override public void run() {
                String url = "cloud".equals(where) ? CLOUD : "http://" + ip.trim() + (ip.contains(":") ? "" : ":8000") + "/hotel_erp.html";
                prefs.edit().putString("url", url).apply();
                web.clearHistory();
                web.loadUrl(url);
            } });
        }
        @JavascriptInterface
        public String saved() { return prefs.getString("url", ""); }
        @JavascriptInterface
        public void change() {
            runOnUiThread(new Runnable() { @Override public void run() { web.loadUrl(START); } });
        }
        // Backup / Excel / PDF: save to Files or send on WhatsApp, Gmail, Drive
        @JavascriptInterface
        public void save(final String name, final String mime, final String b64) {
            runOnUiThread(new Runnable() { @Override public void run() {
                try {
                    File dir = new File(getCacheDir(), "share"); dir.mkdirs();
                    String safe = name == null ? "file" : name.replaceAll("[^A-Za-z0-9_.-]", "_");
                    try (OutputStream o = new FileOutputStream(new File(dir, safe))) { o.write(Base64.decode(b64, Base64.DEFAULT)); }
                    Uri u = Uri.parse("content://com.aghanya.setupos.share/" + safe);
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                    i.putExtra(Intent.EXTRA_STREAM, u);
                    i.setClipData(ClipData.newRawUri(safe, u));
                    i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(i, "Save or send " + safe));
                } catch (Exception e) { Toast.makeText(MainActivity.this, "Could not save: " + e.getMessage(), Toast.LENGTH_LONG).show(); }
            } });
        }
        // window.print() does nothing in a WebView: print the page (Setu shows only the bill / report when printing)
        @JavascriptInterface
        public void print(final String title) {
            runOnUiThread(new Runnable() { @Override public void run() {
                PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                if (pm == null) return;
                String job = title == null || title.isEmpty() ? "Setu" : title;
                pm.print(job, web.createPrintDocumentAdapter(job), new PrintAttributes.Builder().build());
            } });
        }
        @JavascriptInterface
        public void copy(final String text) {
            runOnUiThread(new Runnable() { @Override public void run() {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Setu", text));
            } });
        }
        @JavascriptInterface
        public void share(final String text) {
            runOnUiThread(new Runnable() { @Override public void run() {
                Intent i = new Intent(Intent.ACTION_SEND);
                i.setType("text/plain");
                i.putExtra(Intent.EXTRA_TEXT, text);
                try { startActivity(Intent.createChooser(i, "Send")); } catch (Exception e) { }
            } });
        }
    }
}
