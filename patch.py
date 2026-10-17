# Appliqué par le workflow après "npx cap sync android" : lecture audio écran éteint.
import os, re

PKG = "io.github.rstefxp.lecteur"
APP = "android/app/src/main/java/" + PKG.replace(".", "/")

# 1. WebView toujours "visible" : l'extinction de l'écran ne met plus la lecture en pause
f = "node_modules/@capacitor/android/capacitor/src/main/java/com/getcapacitor/CapacitorWebView.java"
s = open(f, encoding="utf-8").read()
if "onWindowVisibilityChanged" not in s:
    add = """
    @Override
    protected void onWindowVisibilityChanged(int visibility) {
        super.onWindowVisibilityChanged(android.view.View.VISIBLE);
    }
"""
    i = s.rstrip().rfind("}")
    s = s[:i] + add + "}\n"
    open(f, "w", encoding="utf-8").write(s)

# 2. Service de premier plan (notification + verrou CPU) pendant la lecture
open(APP + "/KeepAliveService.java", "w", encoding="utf-8").write("""package %s;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

public class KeepAliveService extends Service {
    private PowerManager.WakeLock lock;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            nm.createNotificationChannel(new NotificationChannel("lecteur", "Lecture", NotificationManager.IMPORTANCE_LOW));
            b = new Notification.Builder(this, "lecteur");
        } else {
            b = new Notification.Builder(this);
        }
        Notification n = b.setContentTitle("Lecteur")
            .setContentText("Lecture en cours")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setOngoing(true)
            .build();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        } else {
            startForeground(1, n);
        }
        if (lock == null) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "lecteur:play");
            lock.acquire(6 * 60 * 60 * 1000L);
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        if (lock != null && lock.isHeld()) {
            lock.release();
        }
        lock = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
""" % PKG)

# 3. MainActivity : la page signale lecture/pause via NativeBg.playing(true|false)
open(APP + "/MainActivity.java", "w", encoding="utf-8").write("""package %s;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    private boolean running = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().addJavascriptInterface(new Object() {
                @JavascriptInterface
                public void playing(boolean p) {
                    setService(p);
                }
            }, "NativeBg");
        }
    }

    private synchronized void setService(boolean on) {
        try {
            Intent i = new Intent(this, KeepAliveService.class);
            if (on && !running) {
                if (Build.VERSION.SDK_INT >= 26) {
                    startForegroundService(i);
                } else {
                    startService(i);
                }
                running = true;
            } else if (!on && running) {
                stopService(i);
                running = false;
            }
        } catch (Exception e) {
            // jamais bloquant
        }
    }

    @Override
    public void onDestroy() {
        setService(false);
        super.onDestroy();
    }
}
""" % PKG)

# 4. Manifest : permissions + service
m = "android/app/src/main/AndroidManifest.xml"
s = open(m, encoding="utf-8").read()
if "KeepAliveService" not in s:
    s = s.replace("</application>", '    <service android:name=".KeepAliveService" android:exported="false" android:foregroundServiceType="mediaPlayback" />\n    </application>', 1)
    perms = "".join('    <uses-permission android:name="android.permission.%s" />\n' % p for p in ("FOREGROUND_SERVICE", "FOREGROUND_SERVICE_MEDIA_PLAYBACK", "WAKE_LOCK", "POST_NOTIFICATIONS"))
    s = s.replace("</manifest>", perms + "</manifest>", 1)
    open(m, "w", encoding="utf-8").write(s)
print("patch OK")
