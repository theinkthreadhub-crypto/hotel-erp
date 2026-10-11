package com.setupro.student;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

// Student ka apna app: library ka bheja hua link ek baar do, phir har baar seedha apna page
// (attendance In/Out + fee). Link library ke WhatsApp message me aata hai.
public class MainActivity extends Activity {
    static final String HOST = "setu-erp.theinkthreadhub.workers.dev";
    static final String PREFIX = "https://" + HOST + "/s/";
    static final String BASE = "https://" + HOST + "/";
    WebView web;
    SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("student", MODE_PRIVATE);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#eef1f6"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportMultipleWindows(false);
        web.addJavascriptInterface(new Bridge(), "StudentApp");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return outside(r.getUrl()); }
            @SuppressWarnings("deprecation")
            @Override public boolean shouldOverrideUrlLoading(WebView v, String url) { return outside(Uri.parse(url)); }
            @Override public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) { if (r.isForMainFrame()) showOffline(); }
            @SuppressWarnings("deprecation")
            @Override public void onReceivedError(WebView v, int code, String desc, String url) { if (url != null && url.equals(v.getUrl())) showOffline(); }
        });
        setContentView(web);
        if (state != null) { web.restoreState(state); return; }
        start(getIntent());
    }

    @Override
    protected void onNewIntent(Intent i) { super.onNewIntent(i); setIntent(i); start(i); }

    // Link tap kiya ho to wahi save karke kholo; warna saved link; warna "link paste karo" screen
    void start(Intent i) {
        Uri u = i == null ? null : i.getData();
        if (u != null && valid(u.toString())) { prefs.edit().putString("link", u.toString()).apply(); web.loadUrl(u.toString()); return; }
        String saved = prefs.getString("link", "");
        if (valid(saved)) web.loadUrl(saved); else showSetup(null);
    }

    static boolean valid(String url) { return url != null && url.startsWith(PREFIX) && url.length() > PREFIX.length() + 3; }

    boolean outside(Uri u) {
        String sc = u.getScheme() == null ? "" : u.getScheme();
        if ((sc.equals("https") || sc.equals("http")) && HOST.equals(u.getHost())) return false;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (ActivityNotFoundException e) { }
        return true;
    }

    void showSetup(String err) {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
            + "<body style='font-family:sans-serif;background:#eef1f6;color:#1d2433;margin:0;padding:28px 20px;text-align:center'>"
            + "<div style='font-size:54px'>📚</div><h2 style='color:#1f3a63;margin:6px 0'>My Library</h2>"
            + "<p style='color:#6b7385;margin:0 0 18px'>Library ne WhatsApp par jo link bheja hai wo yahan paste karein.<br>Phir har baar seedha aapka apna page khulega.</p>"
            + (err == null ? "" : "<p style='color:#c62828;font-weight:600'>" + err + "</p>")
            + "<input id='l' placeholder='https://setu-erp...workers.dev/s/...' style='width:100%;box-sizing:border-box;padding:13px;font-size:15px;border:1px solid #cdd4e1;border-radius:10px'>"
            + "<button onclick=\"var v=document.getElementById('l').value;StudentApp.open(v)\" style='width:100%;margin-top:12px;background:#2b4c7e;color:#fff;border:0;border-radius:10px;padding:14px;font-size:16px;font-weight:600'>Open my app</button>"
            + "<button onclick=\"document.getElementById('l').value=StudentApp.clip()\" style='width:100%;margin-top:10px;background:#fff;color:#2b4c7e;border:1px solid #2b4c7e;border-radius:10px;padding:13px;font-size:15px;font-weight:600'>Paste from clipboard</button>"
            + "<p style='margin-top:30px;color:#6b7385;font-size:13px'>Link nahi mila? Apni library se sampark karein.</p></body></html>";
        web.loadDataWithBaseURL(BASE, html, "text/html", "utf-8", null);
    }

    void showOffline() {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
            + "<body style='font-family:sans-serif;background:#eef1f6;color:#1d2433;text-align:center;padding:60px 24px'>"
            + "<h2 style='color:#1f3a63'>No internet</h2><p>Internet chalu karke dobara try karein.</p>"
            + "<button onclick='StudentApp.reload()' style='background:#2b4c7e;color:#fff;border:0;border-radius:10px;padding:13px 28px;font-size:16px'>Try again</button>"
            + "<p style='margin-top:36px'><a href='#' onclick='StudentApp.reset();return false' style='color:#6b7385;font-size:13px'>Link badalna hai?</a></p></body></html>";
        web.loadDataWithBaseURL(BASE, html, "text/html", "utf-8", null);
    }

    @Override
    public void onBackPressed() { if (web.canGoBack()) web.goBack(); else super.onBackPressed(); }

    @Override protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }
    @Override protected void onResume() { super.onResume(); web.onResume(); }
    @Override protected void onPause() { web.onPause(); super.onPause(); }

    class Bridge {
        @JavascriptInterface
        public void open(final String url) {
            final String u = url == null ? "" : url.trim();
            runOnUiThread(new Runnable() { @Override public void run() {
                if (!valid(u)) { showSetup("Ye sahi student link nahi hai. Poora link paste karein."); return; }
                prefs.edit().putString("link", u).apply();
                web.loadUrl(u);
            } });
        }

        @JavascriptInterface
        public String clip() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                ClipData d = cm.getPrimaryClip();
                if (d != null && d.getItemCount() > 0 && d.getItemAt(0).getText() != null) {
                    String t = d.getItemAt(0).getText().toString();
                    int i = t.indexOf(PREFIX);          // message ke beech se link nikaalo
                    if (i >= 0) { int e = i; while (e < t.length() && !Character.isWhitespace(t.charAt(e))) e++; return t.substring(i, e); }
                    return t.trim();
                }
            } catch (Exception e) { }
            return "";
        }

        @JavascriptInterface
        public void reload() {
            runOnUiThread(new Runnable() { @Override public void run() { start(null); } });
        }

        // "Not you? / link badlo" — student page ya offline page se
        @JavascriptInterface
        public void reset() {
            runOnUiThread(new Runnable() { @Override public void run() { prefs.edit().remove("link").apply(); showSetup(null); } });
        }
    }
}
