"""Native KineticDesk window and lifecycle for the local service."""
import socket
import sys
from threading import Thread

import objc
import uvicorn
from AppKit import (
    NSAlert,
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSTextField,
    NSVariableStatusItemLength,
    NSView,
    NSWindow,
    NSWorkspace,
    NSWorkspaceScreensDidSleepNotification,
    NSWorkspaceSessionDidResignActiveNotification,
    NSWorkspaceWillSleepNotification,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Foundation import (
    NSActivityUserInitiatedAllowingIdleSystemSleep,
    NSObject,
    NSProcessInfo,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
    NSURL,
    NSURLRequest,
    NSUserDefaults,
)
from PyObjCTools import AppHelper
from WebKit import (
    WKWebView,
    WKWebViewConfiguration,
    WKWebsiteDataStore,
)

from kineticdesk.api import create_app
from kineticdesk.config import load_language
from kineticdesk.runtime import Runtime

ACCESSIBILITY_OFFERED_KEY = "KineticDeskAccessibilityOffered"
ACCESSIBILITY_SETTINGS = (
    "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility"
)


NATIVE_COPY = {
    "en": {
        "loading": "Starting KineticDesk…",
        "access": "Open Accessibility…",
        "pause": "Pause Desktop Control",
        "open": "Open Studio",
        "stop": "Stop Camera",
        "active": "Desktop control active · Camera on",
        "camera": "Camera on · Desktop control paused or inactive",
        "off": "Camera off",
        "hide": "Hide KineticDesk",
        "quit": "Quit KineticDesk",
        "launch_failed": "KineticDesk couldn't start",
        "restart": "Quit and reopen the app to restart its local service.",
    },
    "it": {
        "loading": "Avvio di KineticDesk…",
        "access": "Apri Accessibilità…",
        "pause": "Metti in pausa il controllo desktop",
        "open": "Apri Studio",
        "stop": "Spegni fotocamera",
        "active": "Controllo desktop attivo · Fotocamera accesa",
        "camera": "Fotocamera accesa · Controllo desktop in pausa o inattivo",
        "off": "Fotocamera spenta",
        "hide": "Nascondi KineticDesk",
        "quit": "Esci da KineticDesk",
        "launch_failed": "Impossibile avviare KineticDesk",
        "restart": "Chiudi e riapri l’app per riavviare il servizio locale.",
    },
}


class StudioDelegate(NSObject, protocols=[objc.protocolNamed("WKNavigationDelegate")]):
    def applicationDidFinishLaunching_(self, _notification):
        self.language = load_language()
        self.installMenu()
        frame = NSMakeRect(0, 0, 1220, 850)
        style = (
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False,
        )
        self.window.setTitle_("KineticDesk")
        self.window.setReleasedWhenClosed_(False)
        self.window.setRestorable_(False)
        self.window.setDelegate_(self)
        self.window.center()

        loading = NSTextField.labelWithString_(NATIVE_COPY[self.language]["loading"])
        loading.setFrame_(NSMakeRect(24, 790, 350, 24))
        self.window.contentView().addSubview_(loading)
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

        self.runtime = None
        self.server = None
        self.thread = None
        self.listener = None
        self.poller = None
        self.lifecycle_timer = None
        self.web = None
        self.status_item = None
        self.status_state = None
        self.activity = None
        self.workspace_notifications = None
        try:
            self.listener = socket.socket()
            self.listener.bind(("127.0.0.1", 0))
            self.port = self.listener.getsockname()[1]
            self.defaults = NSUserDefaults.standardUserDefaults()
            self.runtime = Runtime(
                open_accessibility=self.queueAccessibility,
                accessibility_offered=self.defaults.boolForKey_(ACCESSIBILITY_OFFERED_KEY),
                native_window=True,
                language_changed=self.queueLanguageChange,
            )
            if self.runtime.device["accessibility"]:
                self.rememberAccessibilityOffer()
            self.server = uvicorn.Server(uvicorn.Config(
                create_app(self.port, self.runtime),
                host="127.0.0.1", port=self.port, loop="asyncio",
                http="h11", ws="websockets", lifespan="on", ws_max_size=4096,
                timeout_graceful_shutdown=2, access_log=False,
                ws_ping_interval=2, ws_ping_timeout=2,
            ))
            self.thread = Thread(
                target=self.server.run,
                kwargs={"sockets": [self.listener]}, name="studio-service", daemon=True,
            )
            self.thread.start()
        except Exception:
            self.showLaunchError()
            return
        self.installStatusMenu()
        self.workspace_notifications = NSWorkspace.sharedWorkspace().notificationCenter()
        for name in (
            NSWorkspaceWillSleepNotification, NSWorkspaceScreensDidSleepNotification,
            NSWorkspaceSessionDidResignActiveNotification,
        ):
            self.workspace_notifications.addObserver_selector_name_object_(
                self, "suspendSession:", name, None,
            )
        self.poller = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            .05, self, "loadWhenReady:", None, True,
        )
        self.lifecycle_timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            .35, self, "pulseStudio:", None, True,
        )
        NSRunLoop.mainRunLoop().addTimer_forMode_(self.lifecycle_timer, NSRunLoopCommonModes)

    @objc.python_method
    def installMenu(self):
        menu = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        menu.addItem_(app_item)
        app_menu = NSMenu.alloc().initWithTitle_("KineticDesk")
        copy = NATIVE_COPY[self.language]
        access = app_menu.addItemWithTitle_action_keyEquivalent_(
            copy["access"], "requestAccessibility:", "",
        )
        access.setTarget_(self)
        pause = app_menu.addItemWithTitle_action_keyEquivalent_(
            copy["pause"], "pauseDesktop:", "",
        )
        pause.setTarget_(self)
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_(copy["hide"], "hide:", "h")
        app_menu.addItemWithTitle_action_keyEquivalent_(copy["quit"], "terminate:", "q")
        app_item.setSubmenu_(app_menu)
        NSApp.setMainMenu_(menu)

    @objc.python_method
    def installStatusMenu(self):
        if self.status_item is None:
            self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength,
            )
        copy = NATIVE_COPY[self.language]
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        self.status_summary = menu.addItemWithTitle_action_keyEquivalent_(copy["off"], None, "")
        self.status_summary.setEnabled_(False)
        menu.addItem_(NSMenuItem.separatorItem())
        for title, action in (
            (copy["open"], "showStudio:"), (copy["pause"], "pauseDesktop:"),
            (copy["stop"], "stopCamera:"),
        ):
            item = menu.addItemWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            if action == "pauseDesktop:":
                self.status_pause = item
            elif action == "stopCamera:":
                self.status_stop = item
        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = menu.addItemWithTitle_action_keyEquivalent_(copy["quit"], "terminate:", "")
        quit_item.setTarget_(NSApp)
        self.status_item.setMenu_(menu)
        self.status_state = None
        self.updateStatusMenu()

    @objc.python_method
    def updateStatusMenu(self):
        active, camera = self.runtime.native_status()
        if (active, camera) == self.status_state:
            return
        self.status_state = active, camera
        copy = NATIVE_COPY[self.language]
        summary = copy["active"] if active else copy["camera"] if camera else copy["off"]
        button = self.status_item.button()
        button.setTitle_("KD ●" if active else "KD ◉" if camera else "KD")
        button.setToolTip_(f"KineticDesk · {summary}")
        button.setAccessibilityLabel_(f"KineticDesk · {summary}")
        self.status_summary.setTitle_(summary)
        self.status_pause.setEnabled_(active)
        self.status_stop.setEnabled_(camera)

        process = NSProcessInfo.processInfo()
        if active and self.activity is None:
            self.activity = process.beginActivityWithOptions_reason_(
                NSActivityUserInitiatedAllowingIdleSystemSleep, "KineticDesk desktop control",
            )
        elif not active and self.activity is not None:
            process.endActivity_(self.activity)
            self.activity = None

    def pulseStudio_(self, _timer):
        self.runtime.pulse_native_window()
        self.updateStatusMenu()

    def pauseDesktop_(self, _sender):
        if self.runtime is not None:
            self.runtime.pause_desktop()
            self.updateStatusMenu()

    def stopCamera_(self, _sender):
        self.runtime.stop()
        self.updateStatusMenu()

    def suspendSession_(self, _notification):
        self.runtime.stop("system-suspension")
        self.updateStatusMenu()

    def showStudio_(self, _sender):
        NSApp.unhide_(None)
        if self.window.isMiniaturized():
            self.window.deminiaturize_(None)
        if self.runtime is not None:
            self.runtime.set_native_background(False)
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        if self.web is None and self.server is not None and self.server.started:
            self.loadStudio()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _visible):
        self.showStudio_(None)
        return False

    def windowShouldClose_(self, window):
        self.applicationDidHide_(None)
        window.orderOut_(None)
        if self.web is not None:
            self.runtime.detach_studio()
            self.web.setNavigationDelegate_(None)
            self.web.stopLoading()
            window.setContentView_(NSView.alloc().initWithFrame_(self.web.bounds()))
            self.web = None
        return False

    def applicationDidHide_(self, _notification):
        if self.runtime is not None:
            self.runtime.set_native_background(True)
            self.updateStatusMenu()

    def windowDidMiniaturize_(self, _notification):
        self.applicationDidHide_(_notification)

    def windowDidBecomeKey_(self, _notification):
        runtime = getattr(self, "runtime", None)
        if runtime is not None:
            runtime.set_native_background(False)

    def webViewWebContentProcessDidTerminate_(self, web):
        if web == self.web:
            self.runtime.detach_studio()
            web.reload()

    @objc.python_method
    def queueLanguageChange(self, language):
        AppHelper.callAfter(self.changeLanguage, language)

    @objc.python_method
    def changeLanguage(self, language):
        self.language = language
        self.installMenu()
        self.installStatusMenu()

    @objc.python_method
    def queueAccessibility(self):
        AppHelper.callAfter(self.requestAccessibility_, None)

    @objc.python_method
    def rememberAccessibilityOffer(self):
        self.defaults.setBool_forKey_(True, ACCESSIBILITY_OFFERED_KEY)
        self.runtime.mark_accessibility_offered()

    def requestAccessibility_(self, _sender):
        if self.runtime is not None:
            self.rememberAccessibilityOffer()
        # Ask macOS to register this app before opening the permission pane.
        trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        if not trusted:
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(ACCESSIBILITY_SETTINGS))
        if self.runtime is not None:
            self.runtime.refresh_permissions()

    def applicationDidBecomeActive_(self, _notification):
        runtime = getattr(self, "runtime", None)
        if runtime is not None:
            runtime.refresh_permissions()

    def loadWhenReady_(self, timer):
        if self.server.started:
            timer.invalidate()
            if self.window.isVisible() and self.web is None:
                self.loadStudio()
        elif not self.thread.is_alive():
            timer.invalidate()
            self.showLaunchError()

    @objc.python_method
    def loadStudio(self):
        config = WKWebViewConfiguration.alloc().init()
        config.setLimitsNavigationsToAppBoundDomains_(True)
        config.setWebsiteDataStore_(WKWebsiteDataStore.nonPersistentDataStore())
        self.web = WKWebView.alloc().initWithFrame_configuration_(
            self.window.contentView().bounds(), config,
        )
        self.web.setNavigationDelegate_(self)
        self.window.setContentView_(self.web)
        url = NSURL.URLWithString_(f"http://127.0.0.1:{self.port}/")
        self.web.loadRequest_(NSURLRequest.requestWithURL_(url))

    @objc.python_method
    def showLaunchError(self, details=None):
        alert = NSAlert.alloc().init()
        copy = NATIVE_COPY[self.language]
        alert.setMessageText_(copy["launch_failed"])
        alert.setInformativeText_(details or copy["restart"])
        alert.runModal()
        NSApp.terminate_(None)

    def webView_didFailProvisionalNavigation_withError_(self, _view, _navigation, error):
        self.showLaunchError(error.localizedDescription())

    def applicationShouldTerminateAfterLastWindowClosed_(self, _application):
        return False

    def applicationWillTerminate_(self, _notification):
        if self.poller is not None:
            self.poller.invalidate()
        if self.lifecycle_timer is not None:
            self.lifecycle_timer.invalidate()
        if self.workspace_notifications is not None:
            self.workspace_notifications.removeObserver_(self)
        if self.activity is not None:
            NSProcessInfo.processInfo().endActivity_(self.activity)
            self.activity = None
        if self.status_item is not None:
            NSStatusBar.systemStatusBar().removeStatusItem_(self.status_item)
        if self.runtime is not None:
            self.runtime.stop("shutdown")
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.5)
        if self.listener is not None:
            self.listener.close()


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = StudioDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import cv2
        import mediapipe as mp
        import numpy as np

        from kineticdesk.assets import MODEL, STUDIO
        from kineticdesk.replay import poses

        assert (STUDIO / "index.html").is_file() and poses()
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
        )
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
            blank = cv2.cvtColor(np.zeros((64, 64, 3), dtype=np.uint8), cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=blank)
            assert not tracker.detect(image).hand_landmarks
        print("KineticDesk bundle check passed.")
    else:
        main()
