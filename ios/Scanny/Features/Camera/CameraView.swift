import AVFoundation
import Observation
import SwiftUI
import UIKit

@Observable
final class CameraController: NSObject, AVCapturePhotoCaptureDelegate {
    let session = AVCaptureSession()
    var isReady = false
    var permissionDenied = false
    var errorMessage: String?
    var flashEnabled = false
    var hasFlash = false
    var onPhoto: ((Data) -> Void)?

    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "com.scanny.camera.session", qos: .userInitiated)
    private var device: AVCaptureDevice?

    func start() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: configureAndStart()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async { if !granted { self?.permissionDenied = true } }
                if granted { self?.configureAndStart() }
            }
        default: permissionDenied = true
        }
    }

    func stop() { queue.async { [weak self] in if self?.session.isRunning == true { self?.session.stopRunning() } } }

    private func configureAndStart() {
        queue.async { [weak self] in
            guard let self else { return }
            if self.session.inputs.isEmpty {
                self.session.beginConfiguration(); self.session.sessionPreset = .photo
                defer { self.session.commitConfiguration() }
                guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                      let input = try? AVCaptureDeviceInput(device: camera), self.session.canAddInput(input), self.session.canAddOutput(self.output)
                else { DispatchQueue.main.async { self.errorMessage = "The rear camera is unavailable." }; return }
                self.session.addInput(input); self.session.addOutput(self.output)
                self.output.maxPhotoQualityPrioritization = .quality
                self.device = camera
                DispatchQueue.main.async { self.hasFlash = camera.hasFlash }
            }
            if !self.session.isRunning { self.session.startRunning() }
            DispatchQueue.main.async { self.isReady = true }
        }
    }

    func capture() {
        guard isReady else { return }
        let settings = AVCapturePhotoSettings(format: [AVVideoCodecKey: AVVideoCodecType.jpeg])
        settings.photoQualityPrioritization = .balanced
        if hasFlash { settings.flashMode = flashEnabled ? .on : .off }
        if let connection = output.connection(with: .video) {
            let angle = Self.videoRotationAngle
            if connection.isVideoRotationAngleSupported(angle) { connection.videoRotationAngle = angle }
        }
        output.capturePhoto(with: settings, delegate: self)
    }

    func focus(at point: CGPoint) {
        guard let device else { return }
        queue.async {
            do {
                try device.lockForConfiguration()
                if device.isFocusPointOfInterestSupported { device.focusPointOfInterest = point; device.focusMode = .autoFocus }
                if device.isExposurePointOfInterestSupported { device.exposurePointOfInterest = point; device.exposureMode = .continuousAutoExposure }
                device.unlockForConfiguration()
            } catch {}
        }
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        guard error == nil, let data = photo.fileDataRepresentation() else {
            DispatchQueue.main.async { self.errorMessage = error?.localizedDescription ?? "This photo could not be captured." }
            return
        }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let jpeg = ImageUtilities.uploadJPEG(from: data) else { return }
            DispatchQueue.main.async { self?.onPhoto?(jpeg) }
        }
    }

    private static var videoRotationAngle: CGFloat {
        switch UIDevice.current.orientation {
        case .landscapeLeft: 0
        case .landscapeRight: 180
        case .portraitUpsideDown: 270
        default: 90
        }
    }
}

struct CameraView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    @State private var camera = CameraController()
    @State private var shutterPulse = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            CameraPreview(session: camera.session, focus: camera.focus)
                .ignoresSafeArea()
            if camera.permissionDenied {
                ContentUnavailableView("Camera access is off", systemImage: "camera.fill", description: Text("Enable Camera access for Scanny in Settings."))
                    .foregroundStyle(.white)
            } else if let error = camera.errorMessage {
                Text(error).foregroundStyle(.white).padding().background(.black.opacity(0.65), in: RoundedRectangle(cornerRadius: 12))
            } else if !camera.isReady { ProgressView().tint(.white).controlSize(.large) }

            VStack {
                HStack {
                    Button { dismiss() } label: { Image(systemName: "xmark").frame(width: 44, height: 44).background(.black.opacity(0.48), in: Circle()) }
                    Spacer()
                    if camera.hasFlash {
                        Button { camera.flashEnabled.toggle() } label: {
                            Image(systemName: camera.flashEnabled ? "bolt.fill" : "bolt.slash.fill").frame(width: 44, height: 44).background(.black.opacity(0.48), in: Circle())
                        }
                    }
                }.font(.headline).foregroundStyle(.white).padding(.horizontal, 18).padding(.top, 8)
                Spacer()
                captureStatus
                Button {
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    withAnimation(.easeOut(duration: 0.12)) { shutterPulse = true }
                    camera.capture()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.14) { withAnimation { shutterPulse = false } }
                } label: {
                    Circle().fill(.white).frame(width: 76, height: 76)
                        .overlay(Circle().stroke(Color.scannyRed, lineWidth: 5).padding(6))
                        .scaleEffect(shutterPulse ? 0.9 : 1)
                }
                .disabled(!camera.isReady).padding(.bottom, 25)
            }
        }
        .statusBarHidden()
        .onAppear {
            camera.onPhoto = { jpeg in state.captureQueue.enqueue(jpeg: jpeg) }
            camera.start()
        }
        .onDisappear { camera.stop() }
    }

    @ViewBuilder private var captureStatus: some View {
        let active = state.captureQueue.activeCount
        let failed = state.captureQueue.failedCount
        if active > 0 || failed > 0 {
            HStack(spacing: 8) {
                if active > 0 { ProgressView().tint(.white); Text("\(active) processing") }
                if failed > 0 { Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.red); Text("\(failed) failed") }
            }
            .font(.caption.weight(.semibold)).foregroundStyle(.white).padding(.horizontal, 13).padding(.vertical, 9)
            .background(.black.opacity(0.58), in: Capsule()).padding(.bottom, 16)
        }
    }
}

private struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession
    let focus: (CGPoint) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(focus: focus) }
    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView(); view.previewLayer.session = session; view.previewLayer.videoGravity = .resizeAspectFill
        let tap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.tapped(_:)))
        view.addGestureRecognizer(tap); context.coordinator.view = view
        return view
    }
    func updateUIView(_ view: PreviewView, context: Context) { view.previewLayer.session = session }

    final class Coordinator: NSObject {
        weak var view: PreviewView?
        let focus: (CGPoint) -> Void
        init(focus: @escaping (CGPoint) -> Void) { self.focus = focus }
        @objc func tapped(_ recognizer: UITapGestureRecognizer) {
            guard let view else { return }
            focus(view.previewLayer.captureDevicePointConverted(fromLayerPoint: recognizer.location(in: view)))
        }
    }
}

private final class PreviewView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}
