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
    NSTextField,
    NSWindow,
    NSWorkspace,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Foundation import NSObject, NSTimer, NSURL, NSURLRequest
from PyObjCTools import AppHelper
from WebKit import (
    WKWebView,
    WKWebViewConfiguration,
    WKWebsiteDataStore,
)

from kineticdesk.api import create_app
from kineticdesk.runtime import Runtime

ACCESSIBILITY_SETTINGS = (
    "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility"
)


class StudioDelegate(NSObject, protocols=[objc.protocolNamed("WKNavigationDelegate")]):
    def applicationDidFinishLaunching_(self, _notification):
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
        self.window.center()

        loading = NSTextField.labelWithString_("Avvio di KineticDesk…")
        loading.setFrame_(NSMakeRect(24, 790, 350, 24))
        self.window.contentView().addSubview_(loading)
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

        self.runtime = None
        self.server = None
        self.thread = None
        self.listener = None
        self.poller = None
        try:
            self.listener = socket.socket()
            self.listener.bind(("127.0.0.1", 0))
            self.port = self.listener.getsockname()[1]
            self.runtime = Runtime(open_accessibility=self.queueAccessibility)
            self.server = uvicorn.Server(uvicorn.Config(
                create_app(self.port, self.runtime),
                host="127.0.0.1", port=self.port, loop="asyncio",
                http="h11", ws="websockets", lifespan="on", ws_max_size=4096,
                timeout_graceful_shutdown=2, access_log=False,
            ))
            self.thread = Thread(
                target=self.server.run,
                kwargs={"sockets": [self.listener]}, name="studio-service", daemon=True,
            )
            self.thread.start()
        except Exception:
            self.showLaunchError()
            return
        self.poller = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            .05, self, "loadWhenReady:", None, True,
        )

    @objc.python_method
    def installMenu(self):
        menu = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        menu.addItem_(app_item)
        app_menu = NSMenu.alloc().initWithTitle_("KineticDesk")
        access = app_menu.addItemWithTitle_action_keyEquivalent_(
            "Autorizza Accessibilità…", "requestAccessibility:", "",
        )
        access.setTarget_(self)
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_("Esci da KineticDesk", "terminate:", "q")
        app_item.setSubmenu_(app_menu)
        NSApp.setMainMenu_(menu)

    @objc.python_method
    def queueAccessibility(self):
        AppHelper.callAfter(self.requestAccessibility_, None)

    def requestAccessibility_(self, _sender):
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
        elif not self.thread.is_alive():
            timer.invalidate()
            self.showLaunchError()

    @objc.python_method
    def showLaunchError(self, details=None):
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Impossibile avviare KineticDesk")
        alert.setInformativeText_(
            details or "Chiudi e riapri l’app per riavviare il servizio locale.",
        )
        alert.runModal()
        NSApp.terminate_(None)

    def webView_didFailProvisionalNavigation_withError_(self, _view, _navigation, error):
        self.showLaunchError(error.localizedDescription())

    def applicationShouldTerminateAfterLastWindowClosed_(self, _application):
        return True

    def applicationWillTerminate_(self, _notification):
        if self.poller is not None:
            self.poller.invalidate()
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
