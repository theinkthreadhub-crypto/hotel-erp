package com.setupro.library;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

// Setu Library: owner ka phone app. Setu Pro cloud ka Online View (/view) WebView mein kholta hai.
public class MainActivity extends Activity {
    static final String HOST = "setu-erp.theinkthreadhub.workers.dev";
    static final String START = "https://" + HOST + "/view";
    WebView web;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#F4F6FA"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // login (Library ID + PIN) yaad rakhne ke liye
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportMultipleWindows(false);
        s.setUserAgentString(s.getUserAgentString() + " SetuLibraryApp/1.0");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return openOutside(r.getUrl());
            }
            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) {
                return openOutside(Uri.parse(url));
            }
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
        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(START);
    }

    // Apni site app ke andar; WhatsApp, phone call, baaki links bahar wale app mein
    boolean openOutside(Uri u) {
        String scheme = u.getScheme() == null ? "" : u.getScheme();
        if ((scheme.equals("https") || scheme.equals("http")) && HOST.equals(u.getHost())) return false;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { }
        return true;
    }

    void showOffline() {
        String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
            + "<body style='font-family:sans-serif;background:#f4f6fa;color:#1d2433;text-align:center;padding:60px 24px'>"
            + "<h2 style='color:#2b4c7e'>No internet</h2><p>Connect to the internet and try again.</p>"
            + "<button onclick=\"location.href='" + START + "'\" style='background:#2b4c7e;color:#fff;border:0;border-radius:8px;padding:12px 28px;font-size:16px'>Try again</button>"
            + "<p style='margin-top:40px;color:#6b7385;font-size:13px'>Setu Pro &middot; 6392995127</p></body></html>";
        web.loadDataWithBaseURL(START, html, "text/html", "utf-8", START);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
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
}
