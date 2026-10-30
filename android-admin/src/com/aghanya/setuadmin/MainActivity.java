package com.aghanya.setuadmin;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.KeyguardManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

// Setu Hotel Super Admin app (v2): a native shell around Setu Cloud's /admin.html.
// Native: splash, app lock (fingerprint / screen lock), Admin Key kept in the Android Keystore, loading bar,
// offline screen that retries by itself, system bar colours, haptics, back button, file save / share.
// The screens themselves come from the live admin.html (app mode), so most changes need no new APK.
public class MainActivity extends Activity {
    static final String HOST = "setu-cloud.theinkthreadhub.workers.dev";
    static final String START = "https://" + HOST + "/admin.html";
    static final String VERSION = "2.1";
    static final int PICK = 7, LOCK_REQ = 8;
    static final String NIGHT = "#0E0B09", INK = "#F8F3EE", MUTED = "#A39A92";   // dark glass look
    static final long RELOCK_MS = 60_000;          // locked again after a minute in the background

    WebView web;
    FrameLayout root;
    View splash, offline, lockView;
    ProgressBar bar;
    ValueCallback<Uri[]> pick;
    SharedPreferences prefs;
    final Handler ui = new Handler(Looper.getMainLooper());
    boolean pageReady, locked, authBusy;
    long pausedAt, lastBack;
    ConnectivityManager.NetworkCallback netCb;

    @SuppressWarnings("deprecation")
    int brandColor() { return getResources().getColor(R.color.brand); }

    int dp(float v) { return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics())); }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("setu_admin", MODE_PRIVATE);
        if (lockOn()) getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);   // no admin data in "recent apps"
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor(NIGHT));

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor(NIGHT));
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setVerticalScrollBarEnabled(false);
        web.setHorizontalScrollBarEnabled(false);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setSupportMultipleWindows(false);
        s.setTextZoom(100);                          // big system font must not break the layout
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        if (Build.VERSION.SDK_INT >= 26) s.setSafeBrowsingEnabled(true);
        s.setUserAgentString(s.getUserAgentString() + " SetuHotelAdminApp/" + VERSION);
        web.addJavascriptInterface(new Bridge(), "SA");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return openOutside(r.getUrl()); }
            @SuppressWarnings("deprecation")
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) { return openOutside(Uri.parse(url)); }
            @Override
            public void onPageFinished(WebView v, String url) {
                // The page says when its first screen is drawn (SA.ready); this is only the fallback
                ui.postDelayed(new Runnable() { @Override public void run() { hideSplash(); } }, 2500);
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
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int p) {
                bar.setProgress(p);
                bar.setVisibility(p >= 100 ? View.GONE : View.VISIBLE);
            }
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (pick != null) pick.onReceiveValue(null);
                pick = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try { startActivityForResult(Intent.createChooser(i, "File chuniye"), PICK); }
                catch (Exception e) { pick = null; return false; }
                return true;
            }
            // Native dialogs for any alert() / confirm() the page still uses
            @Override
            public boolean onJsAlert(WebView v, String url, String msg, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this, R.style.Dialog).setMessage(msg).setCancelable(false)
                    .setPositiveButton("OK", (d, w) -> r.confirm()).show();
                return true;
            }
            @Override
            public boolean onJsConfirm(WebView v, String url, String msg, final JsResult r) {
                new AlertDialog.Builder(MainActivity.this, R.style.Dialog).setMessage(msg)
                    .setPositiveButton("Haan", (d, w) -> r.confirm())
                    .setNegativeButton("Nahi", (d, w) -> r.cancel())
                    .setOnCancelListener(d -> r.cancel()).show();
                return true;
            }
        });
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));

        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setProgressTintList(android.content.res.ColorStateList.valueOf(brandColor()));
        bar.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.TRANSPARENT));
        FrameLayout.LayoutParams bl = new FrameLayout.LayoutParams(-1, dp(3), Gravity.TOP);
        bl.topMargin = -dp(6);                        // hide the bar's own padding
        root.addView(bar, bl);

        splash = buildSplash();
        root.addView(splash, new FrameLayout.LayoutParams(-1, -1));
        offline = buildOffline();
        offline.setVisibility(View.GONE);
        root.addView(offline, new FrameLayout.LayoutParams(-1, -1));
        lockView = buildLock();
        lockView.setVisibility(View.GONE);
        root.addView(lockView, new FrameLayout.LayoutParams(-1, -1));

        setContentView(root);
        getWindow().setBackgroundDrawable(null);     // the launch logo is no longer needed behind the app
        systemBars(NIGHT, false);

        if (state != null) web.restoreState(state);
        else web.loadUrl(START);
        // A splash that never goes away would look like a hang: at most 8 seconds
        ui.postDelayed(new Runnable() { @Override public void run() { hideSplash(); } }, 8000);
        if (lockOn()) ui.post(new Runnable() { @Override public void run() { lock(); } });   // after the window is up
        watchNetwork();
    }

    // ---------- native screens ----------
    View buildSplash() {
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL);
        v.setGravity(Gravity.CENTER);
        v.setBackground(glow());
        v.setClickable(true);
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.splash_logo);
        v.addView(logo, new LinearLayout.LayoutParams(dp(108), dp(108)));
        TextView t = text("Setu Hotel Admin", 22, INK, true);
        t.setPadding(0, dp(20), 0, dp(4));
        v.addView(t);
        v.addView(text("Aghanya Devanya Enterprises", 13, MUTED, false));
        ProgressBar p = new ProgressBar(this);
        p.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(brandColor()));
        LinearLayout.LayoutParams pl = new LinearLayout.LayoutParams(dp(28), dp(28));
        pl.topMargin = dp(36);
        v.addView(p, pl);
        return v;
    }

    View buildOffline() {
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL);
        v.setGravity(Gravity.CENTER);
        v.setPadding(dp(32), 0, dp(32), 0);
        v.setBackground(glow());
        v.setClickable(true);
        TextView icon = text("⚠", 40, "#FF9A3C", false);
        GradientDrawable circle = new GradientDrawable();
        circle.setShape(GradientDrawable.OVAL);
        circle.setColor(Color.parseColor("#1FFFFFFF"));
        circle.setStroke(dp(1), Color.parseColor("#1FFFFFFF"));
        icon.setBackground(circle);
        icon.setGravity(Gravity.CENTER);
        v.addView(icon, new LinearLayout.LayoutParams(dp(88), dp(88)));
        TextView t = text("Internet nahi hai", 22, INK, true);
        t.setPadding(0, dp(20), 0, dp(6));
        v.addView(t);
        TextView d = text("WiFi ya mobile data on kijiye. Internet aate hi Setu Admin apne aap khul jayega.", 14, MUTED, false);
        d.setGravity(Gravity.CENTER);
        v.addView(d);
        Button b = pill("Dobara koshish karein");
        b.setOnClickListener(x -> { haptic("tap"); retry(); });
        LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(-2, dp(48));
        bl.topMargin = dp(28);
        v.addView(b, bl);
        return v;
    }

    View buildLock() {
        LinearLayout v = new LinearLayout(this);
        v.setOrientation(LinearLayout.VERTICAL);
        v.setGravity(Gravity.CENTER);
        v.setBackground(glow());
        v.setClickable(true);
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.splash_logo);
        v.addView(logo, new LinearLayout.LayoutParams(dp(88), dp(88)));
        TextView t = text("Setu Hotel Admin locked", 22, INK, true);
        t.setPadding(0, dp(20), 0, dp(6));
        v.addView(t);
        v.addView(text("Fingerprint ya phone ka screen lock lagaiye", 14, MUTED, false));
        Button b = pill("Unlock");
        b.setOnClickListener(x -> { haptic("tap"); authenticate(); });
        LinearLayout.LayoutParams bl = new LinearLayout.LayoutParams(dp(200), dp(48));
        bl.topMargin = dp(32);
        v.addView(b, bl);
        return v;
    }

    TextView text(String s, float sp, String color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(Color.parseColor(color));
        if (bold) t.setTypeface(android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL));
        return t;
    }

    Button pill(String label) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        b.setPadding(dp(28), 0, dp(28), 0);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{ Color.parseColor("#FF9A3C"), Color.parseColor("#FF6A00") });
        g.setCornerRadius(dp(26));
        b.setBackground(new android.graphics.drawable.RippleDrawable(
            android.content.res.ColorStateList.valueOf(Color.parseColor("#33FFFFFF")), g, null));
        b.setStateListAnimator(null);
        return b;
    }

    // Warm black with an orange glow at the top (same as the page)
    android.graphics.drawable.Drawable glow() {
        return new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            new int[]{ Color.parseColor("#3A1E0C"), Color.parseColor(NIGHT), Color.parseColor(NIGHT) });
    }

    void hideSplash() {
        if (splash.getVisibility() != View.VISIBLE || splash.getAlpha() < 1f) return;
        splash.animate().alpha(0f).setDuration(220).withEndAction(new Runnable() {
            @Override public void run() { splash.setVisibility(View.GONE); }
        }).start();
    }

    void showOffline() {
        if (offline.getVisibility() == View.VISIBLE) return;
        hideSplash();
        offline.setAlpha(0f);
        offline.setVisibility(View.VISIBLE);
        offline.animate().alpha(1f).setDuration(180).start();
        web.loadUrl("about:blank");
    }

    void retry() {
        offline.setVisibility(View.GONE);
        bar.setVisibility(View.VISIBLE);
        web.loadUrl(START);
    }

    // Internet back: open the admin again without a tap
    void watchNetwork() {
        if (Build.VERSION.SDK_INT < 24) return;
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return;
        netCb = new ConnectivityManager.NetworkCallback() {
            @Override public void onAvailable(Network n) {
                ui.post(new Runnable() { @Override public void run() { if (offline.getVisibility() == View.VISIBLE) retry(); } });
            }
        };
        try { cm.registerDefaultNetworkCallback(netCb); } catch (Exception e) { netCb = null; }
    }

    // Status / navigation bar colours follow the screen (the page sends them through SA.bars)
    void systemBars(String color, boolean light) {
        Window w = getWindow();
        int c = Color.parseColor(color);
        w.setStatusBarColor(c);
        w.setNavigationBarColor(light ? Color.WHITE : c);
        View d = w.getDecorView();
        int f = d.getSystemUiVisibility();
        if (Build.VERSION.SDK_INT >= 23) f = light ? f | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR : f & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= 27) f = light ? f | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR : f & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        d.setSystemUiVisibility(f);
    }

    void haptic(String kind) {
        int k = HapticFeedbackConstants.VIRTUAL_KEY;
        if ("long".equals(kind)) k = HapticFeedbackConstants.LONG_PRESS;
        else if (Build.VERSION.SDK_INT >= 30 && "success".equals(kind)) k = HapticFeedbackConstants.CONFIRM;
        else if (Build.VERSION.SDK_INT >= 30 && "error".equals(kind)) k = HapticFeedbackConstants.REJECT;
        else if (Build.VERSION.SDK_INT >= 23 && "tick".equals(kind)) k = HapticFeedbackConstants.CONTEXT_CLICK;
        root.performHapticFeedback(k);
    }

    // Apni site app ke andar; WhatsApp, phone call, baaki links bahar wale app mein
    boolean openOutside(Uri u) {
        String scheme = u.getScheme() == null ? "" : u.getScheme();
        if (scheme.equals("https") && HOST.equals(u.getHost())) return false;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { }
        return true;
    }

    // Native → page events (lock result, …)
    void event(String name, String json) {
        final String js = "window.SAevent&&SAevent('" + name + "'," + json + ")";
        ui.post(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
    }

    // ---------- app lock ----------
    boolean lockOn() { return prefs.getBoolean("lock", false); }

    boolean lockAvailable() {
        KeyguardManager km = (KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
        if (km == null) return false;
        return Build.VERSION.SDK_INT >= 23 ? km.isDeviceSecure() : km.isKeyguardSecure();
    }

    void lock() {
        if (!lockAvailable()) return;              // no screen lock on the phone: nothing to check against
        locked = true;
        lockView.setVisibility(View.VISIBLE);
        authenticate();
    }

    void unlocked() {
        locked = false;
        authBusy = false;
        lockView.animate().alpha(0f).setDuration(200).withEndAction(new Runnable() {
            @Override public void run() { lockView.setVisibility(View.GONE); lockView.setAlpha(1f); }
        }).start();
    }

    // then = what to do after a good check (null = just unlock)
    Runnable afterAuth;
    void authenticate() {
        if (authBusy) return;
        authBusy = true;
        if (Build.VERSION.SDK_INT >= 28) {
            BiometricPrompt.Builder b = new BiometricPrompt.Builder(this)
                .setTitle("Setu Hotel Admin")
                .setSubtitle("Fingerprint ya phone ka screen lock");
            if (Build.VERSION.SDK_INT >= 30) {
                b.setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG | BiometricManager.Authenticators.DEVICE_CREDENTIAL);
            } else if (Build.VERSION.SDK_INT == 29) {
                b.setDeviceCredentialAllowed(true);
            } else {
                b.setNegativeButton("PIN / pattern", getMainExecutor(), (d, w) -> { authBusy = false; credentialScreen(); });
            }
            try {
                b.build().authenticate(new CancellationSignal(), getMainExecutor(), new BiometricPrompt.AuthenticationCallback() {
                    @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult r) { authOk(); }
                    @Override public void onAuthenticationError(int code, CharSequence msg) { authFail(); }
                });
            } catch (Exception e) { authBusy = false; credentialScreen(); }
        } else {
            authBusy = false;
            credentialScreen();
        }
    }

    // Android 5–8 (and a fallback): the phone's own PIN / pattern / password screen
    void credentialScreen() {
        KeyguardManager km = (KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
        Intent i = km == null ? null : km.createConfirmDeviceCredentialIntent("Setu Hotel Admin", "Phone ka screen lock lagaiye");
        if (i == null) { authOk(); return; }
        authBusy = true;
        startActivityForResult(i, LOCK_REQ);
    }

    void authOk() {
        haptic("success");
        Runnable r = afterAuth;
        afterAuth = null;
        if (r != null) { authBusy = false; r.run(); }
        if (locked) unlocked(); else authBusy = false;
    }

    void authFail() {
        authBusy = false;
        if (afterAuth != null) { afterAuth = null; event("lock", "{\"on\":" + lockOn() + ",\"error\":true}"); }
    }

    // ---------- Admin Key in the Android Keystore (never plain on the phone) ----------
    static final String KS_ALIAS = "setu_admin_key";

    SecretKey keystoreKey() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        if (ks.containsAlias(KS_ALIAS)) return ((KeyStore.SecretKeyEntry) ks.getEntry(KS_ALIAS, null)).getSecretKey();
        KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        g.init(new KeyGenParameterSpec.Builder(KS_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build());
        return g.generateKey();
    }

    void keySave(String key) {
        if (key == null || key.isEmpty()) { prefs.edit().remove("k").remove("kp").apply(); return; }
        if (Build.VERSION.SDK_INT < 23) { prefs.edit().putString("kp", key).apply(); return; }
        try {
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, keystoreKey());
            byte[] iv = c.getIV(), ct = c.doFinal(key.getBytes(StandardCharsets.UTF_8));
            prefs.edit().putString("k", Base64.encodeToString(iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(ct, Base64.NO_WRAP)).remove("kp").apply();
        } catch (Exception e) { prefs.edit().remove("k").apply(); }
    }

    String keyLoad() {
        if (Build.VERSION.SDK_INT < 23) return prefs.getString("kp", "");
        String v = prefs.getString("k", "");
        if (v.isEmpty() || !v.contains(":")) return "";
        try {
            String[] p = v.split(":", 2);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, keystoreKey(), new GCMParameterSpec(128, Base64.decode(p[0], Base64.NO_WRAP)));
            return new String(c.doFinal(Base64.decode(p[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
        } catch (Exception e) { return ""; }
    }

    // ---------- lifecycle ----------
    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == PICK && pick != null) {
            pick.onReceiveValue(res == RESULT_OK && data != null && data.getData() != null ? new Uri[]{ data.getData() } : null);
            pick = null;
            return;
        }
        if (req == LOCK_REQ) {
            authBusy = false;
            if (res == RESULT_OK) authOk(); else authFail();
            return;
        }
        super.onActivityResult(req, res, data);
    }

    // Back: the page closes its own sheet / dialog / screen first; on the home list press twice to leave
    @Override
    public void onBackPressed() {
        if (locked) { moveTaskToBack(true); return; }
        if (offline.getVisibility() == View.VISIBLE) { super.onBackPressed(); return; }
        web.evaluateJavascript("(window.SAback?SAback():false)", new ValueCallback<String>() {
            @Override public void onReceiveValue(String handled) {
                if ("true".equals(handled)) return;
                long now = SystemClock.uptimeMillis();
                if (now - lastBack < 2000) { finish(); return; }
                lastBack = now;
                Toast.makeText(MainActivity.this, "Band karne ke liye dobara back dabaiye", Toast.LENGTH_SHORT).show();
            }
        });
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        if (lockOn() && !locked && pausedAt > 0 && SystemClock.elapsedRealtime() - pausedAt > RELOCK_MS) lock();
        pausedAt = 0;
        event("resume", "{}");
    }

    @Override
    protected void onPause() {
        if (!authBusy) pausedAt = SystemClock.elapsedRealtime();
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (netCb != null && Build.VERSION.SDK_INT >= 24) {
            try { ((ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE)).unregisterNetworkCallback(netCb); } catch (Exception e) { }
        }
        ViewGroup p = (ViewGroup) web.getParent();
        if (p != null) p.removeView(web);
        web.destroy();
        super.onDestroy();
    }

    // ---------- the page's bridge (window.SA) ----------
    class Bridge {
        @JavascriptInterface public String version() { return VERSION; }

        @JavascriptInterface public void ready() {
            ui.post(new Runnable() { @Override public void run() { pageReady = true; hideSplash(); } });
        }

        @JavascriptInterface public void bars(final String color, final boolean light) {
            if (color == null || !color.matches("#[0-9A-Fa-f]{6}")) return;
            ui.post(new Runnable() { @Override public void run() { systemBars(color, light); } });
        }

        @JavascriptInterface public void haptic(final String kind) {
            ui.post(new Runnable() { @Override public void run() { MainActivity.this.haptic(kind); } });
        }

        // Admin Key: encrypted with a key that never leaves the phone's Keystore
        @JavascriptInterface public String keyGet() { return keyLoad(); }
        @JavascriptInterface public void keySet(String k) { keySave(k); }
        @JavascriptInterface public void keyClear() { keySave(""); }

        // App lock: {available, on}. Turning it on or off asks for the fingerprint / screen lock first.
        @JavascriptInterface public String lockState() {
            return "{\"available\":" + lockAvailable() + ",\"on\":" + lockOn() + "}";
        }
        @JavascriptInterface public void lockSet(final boolean on) {
            ui.post(new Runnable() { @Override public void run() {
                if (!lockAvailable()) { event("lock", "{\"on\":false,\"error\":\"noscreenlock\"}"); return; }
                afterAuth = new Runnable() { @Override public void run() {
                    prefs.edit().putBoolean("lock", on).apply();
                    if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
                    else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
                    event("lock", "{\"on\":" + on + "}");
                } };
                authenticate();
            } });
        }

        @JavascriptInterface public void copy(final String text) {
            ui.post(new Runnable() { @Override public void run() {
                ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Setu", text));
            } });
        }

        @JavascriptInterface public void share(final String text) {
            ui.post(new Runnable() { @Override public void run() {
                Intent i = new Intent(Intent.ACTION_SEND);
                i.setType("text/plain");
                i.putExtra(Intent.EXTRA_TEXT, text);
                try { startActivity(Intent.createChooser(i, "Bhejiye")); } catch (Exception e) { }
            } });
        }

        // Backup / file save or share (Gmail, WhatsApp, Drive)
        @JavascriptInterface public void save(final String name, final String mime, final String b64) {
            ui.post(new Runnable() { @Override public void run() {
                try {
                    File dir = new File(getCacheDir(), "share"); dir.mkdirs();
                    String safe = name == null ? "file" : name.replaceAll("[^A-Za-z0-9_.-]", "_");
                    try (OutputStream o = new FileOutputStream(new File(dir, safe))) { o.write(Base64.decode(b64, Base64.DEFAULT)); }
                    Uri u = Uri.parse("content://com.aghanya.setuadmin.share/" + safe);
                    Intent i = new Intent(Intent.ACTION_SEND);
                    i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
                    i.putExtra(Intent.EXTRA_STREAM, u);
                    i.setClipData(ClipData.newRawUri(safe, u));
                    i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    startActivity(Intent.createChooser(i, "Save ya bhejiye: " + safe));
                } catch (Exception e) { Toast.makeText(MainActivity.this, "Save nahi hua: " + e.getMessage(), Toast.LENGTH_LONG).show(); }
            } });
        }
    }
}
