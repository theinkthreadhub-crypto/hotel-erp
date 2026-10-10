package com.setupro.libraryerp;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Bundle;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.provider.Settings;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

// Library ERP (phone): wahi app.html, bina computer ke. mobile.js isme "server" ka kaam karta hai,
// aur ye class use phone ki cheezein deti hai: files, internet, share, print, WhatsApp.
public class MainActivity extends Activity {
    static final String BASE = "https://erp.local/";
    static final int PICK_FILE = 7;
    WebView web;
    WebView printView;
    ValueCallback<Uri[]> fileCb;
    File root;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        root = new File(getFilesDir(), "erp");
        root.mkdirs();
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setSupportMultipleWindows(false);
        s.setTextZoom(100);
        web.addJavascriptInterface(new Bridge(), "Android");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return outside(r.getUrl()); }
            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) { return outside(Uri.parse(url)); }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (fileCb != null) fileCb.onReceiveValue(null);
                fileCb = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try { startActivityForResult(Intent.createChooser(i, "Choose file"), PICK_FILE); }
                catch (ActivityNotFoundException e) { fileCb = null; return false; }
                return true;
            }
        });
        setContentView(web);
        web.loadDataWithBaseURL(BASE, page(), "text/html", "utf-8", null);
        // Internet aate hi Setu Pro cloud par backup
        try {
            ((ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE)).registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
                @Override public void onAvailable(Network n) {
                    runOnUiThread(new Runnable() { @Override public void run() { web.evaluateJavascript("window.__netUp&&window.__netUp()", null); } });
                }
            });
        } catch (Exception e) { }
    }

    // app.html + summary.js + mobile.js (mobile.js sabse pehle chalta hai aur /api/* sambhalta hai)
    String page() {
        String app = asset("app.html");
        String inject = "<script>(function(){var module={exports:{}};\n" + asset("summary.js")
            + "\nwindow.LibSummary=module.exports.summary;})();</script><script>" + asset("mobile.js") + "</script>";
        int i = app.indexOf("<head>");
        return i < 0 ? inject + app : app.substring(0, i + 6) + inject + app.substring(i + 6);
    }

    String asset(String name) {
        try (InputStream in = getAssets().open(name)) { return new String(readAll(in), StandardCharsets.UTF_8); }
        catch (Exception e) { return ""; }
    }

    static byte[] readAll(InputStream in) throws java.io.IOException {
        ByteArrayOutputStream o = new ByteArrayOutputStream();
        byte[] b = new byte[16384];
        int n;
        while ((n = in.read(b)) > 0) o.write(b, 0, n);
        return o.toByteArray();
    }

    // WhatsApp, phone, baaki links: bahar wale app mein
    boolean outside(Uri u) {
        if ("erp.local".equals(u.getHost())) return true;
        open(u.toString());
        return true;
    }

    void open(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException e) {
            if (url.startsWith("whatsapp://send")) {  // WhatsApp app nahi hai to wa.me
                Uri u = Uri.parse(url);
                open("https://wa.me/" + u.getQueryParameter("phone") + "?text=" + Uri.encode(u.getQueryParameter("text")));
            } else Toast.makeText(this, "No app found to open this", Toast.LENGTH_SHORT).show();
        }
    }

    File file(String name) {
        if (name == null || name.contains("..") || !name.matches("[A-Za-z0-9_./-]+")) throw new IllegalArgumentException("bad name");
        return new File(root, name);
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req != PICK_FILE || fileCb == null) return;
        Uri u = res == RESULT_OK && data != null ? data.getData() : null;
        fileCb.onReceiveValue(u == null ? null : new Uri[]{u});
        fileCb = null;
    }

    @Override
    public void onBackPressed() {
        web.evaluateJavascript("window.__back?window.__back():'exit'", new ValueCallback<String>() {
            @Override public void onReceiveValue(String v) { if ("\"exit\"".equals(v)) finish(); }
        });
    }

    @Override
    protected void onPause() {
        web.evaluateJavascript("window.__cloudSync&&window.__cloudSync()", null);
        super.onPause();
    }

    class Bridge {
        @JavascriptInterface
        public String config() {
            try {
                JSONObject c = new JSONObject(asset("config.json"));
                c.put("version", getPackageManager().getPackageInfo(getPackageName(), 0).versionName);
                return c.toString();
            } catch (Exception e) { return "{}"; }
        }

        @JavascriptInterface
        public String readFile(String name) {
            try {
                File f = file(name);
                if (!f.exists()) return null;
                try (InputStream in = new java.io.FileInputStream(f)) { return new String(readAll(in), StandardCharsets.UTF_8); }
            } catch (Exception e) { return null; }
        }

        @JavascriptInterface
        public boolean writeFile(String name, String text) {
            try {
                File f = file(name), t = new File(f.getPath() + ".tmp");
                f.getParentFile().mkdirs();
                try (OutputStream o = new FileOutputStream(t)) { o.write(text.getBytes(StandardCharsets.UTF_8)); o.flush(); ((FileOutputStream) o).getFD().sync(); }
                return t.renameTo(f);
            } catch (Exception e) { return false; }
        }

        @JavascriptInterface
        public void deleteFile(String name) { try { file(name).delete(); } catch (Exception e) { } }

        @JavascriptInterface
        public String listFiles(String dir) {
            JSONArray a = new JSONArray();
            try {
                File[] L = file(dir).listFiles();
                if (L != null) for (File f : L) {
                    if (!f.isFile() || f.getName().endsWith(".tmp")) continue;
                    JSONObject o = new JSONObject();
                    o.put("name", f.getName()); o.put("size", f.length()); o.put("time", f.lastModified());
                    a.put(o);
                }
            } catch (Exception e) { }
            return a.toString();
        }

        @JavascriptInterface
        public String machineId() {
            String id = Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
            return id == null ? "android" : id;
        }

        @JavascriptInterface
        public String hash(String alg, String b64) {
            try { return Base64.encodeToString(MessageDigest.getInstance(alg).digest(Base64.decode(b64, Base64.DEFAULT)), Base64.NO_WRAP); }
            catch (Exception e) { return ""; }
        }

        @JavascriptInterface
        public String gzip(String text) {
            try {
                ByteArrayOutputStream o = new ByteArrayOutputStream();
                try (GZIPOutputStream z = new GZIPOutputStream(o)) { z.write(text.getBytes(StandardCharsets.UTF_8)); }
                return Base64.encodeToString(o.toByteArray(), Base64.NO_WRAP);
            } catch (Exception e) { return ""; }
        }

        @JavascriptInterface
        public String gunzip(String b64) {
            try (InputStream in = new GZIPInputStream(new ByteArrayInputStream(Base64.decode(b64, Base64.DEFAULT)))) {
                return new String(readAll(in), StandardCharsets.UTF_8);
            } catch (Exception e) { return ""; }
        }

        @JavascriptInterface
        public void httpPost(final String id, final String url, final String body) {
            new Thread(new Runnable() { @Override public void run() {
                int code = 0;
                String text = "";
                try {
                    HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                    c.setConnectTimeout(20000);
                    c.setReadTimeout(60000);
                    c.setRequestMethod("POST");
                    c.setDoOutput(true);
                    c.setRequestProperty("Content-Type", "application/json");
                    try (OutputStream o = c.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
                    code = c.getResponseCode();
                    InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
                    if (in != null) try (InputStream i = in) { text = new String(readAll(i), StandardCharsets.UTF_8); }
                    c.disconnect();
                } catch (Exception e) { code = 0; text = ""; }
                final String js = "window.__httpCb(" + JSONObject.quote(id) + "," + code + "," + JSONObject.quote(text) + ")";
                runOnUiThread(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
            } }).start();
        }

        @JavascriptInterface
        public void share(final String name, final String b64, final String mime, final String subject) {
            runOnUiThread(new Runnable() { @Override public void run() {
                try {
                    File dir = new File(getCacheDir(), "share");
                    dir.mkdirs();
                    String safe = name.replaceAll("[^A-Za-z0-9_.-]", "_");
                    try (OutputStream o = new FileOutputStream(new File(dir, safe))) { o.write(Base64.decode(b64, Base64.DEFAULT)); }
                    Uri u = Uri.parse("content://com.setupro.libraryerp.share/" + safe);
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                    i.putExtra(Intent.EXTRA_STREAM, u);
                    i.putExtra(Intent.EXTRA_SUBJECT, subject);
                    i.setClipData(ClipData.newRawUri(safe, u));
                    i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(i, "Save or send " + safe));
                } catch (Exception e) {
                    Toast.makeText(MainActivity.this, "Could not share: " + e.getMessage(), Toast.LENGTH_LONG).show();
                }
            } });
        }

        @JavascriptInterface
        public void print(final String html, final String job) {
            runOnUiThread(new Runnable() { @Override public void run() {
                printView = new WebView(MainActivity.this);
                printView.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView v, String url) {
                        PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                        pm.print(job, v.createPrintDocumentAdapter(job), new PrintAttributes.Builder().build());
                    }
                });
                printView.loadDataWithBaseURL(BASE, html, "text/html", "utf-8", null);
            } });
        }

        @JavascriptInterface
        public void openUrl(final String url) { runOnUiThread(new Runnable() { @Override public void run() { open(url); } }); }

        @JavascriptInterface
        public void quit() { runOnUiThread(new Runnable() { @Override public void run() { finishAndRemoveTask(); } }); }
    }
}
