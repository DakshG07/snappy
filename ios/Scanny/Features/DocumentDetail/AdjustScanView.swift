import SwiftUI
import UIKit

private enum ScanCorner: String, CaseIterable, Identifiable {
    case topLeft, topRight, bottomRight, bottomLeft
    var id: Self { self }
    var number: String {
        switch self { case .topLeft: "1"; case .topRight: "2"; case .bottomRight: "3"; case .bottomLeft: "4" }
    }
}

struct AdjustScanView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let document: ScannyDocument
    @State private var image: UIImage?
    @State private var imageSize: CGSize = .zero
    @State private var points: [ScanCorner: CGPoint] = [:]
    @State private var mode: ScanMode
    @State private var saving = false
    @State private var error: String?

    init(document: ScannyDocument) {
        self.document = document
        _mode = State(initialValue: document.scanMode)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 14) {
                Picker("Output", selection: $mode) {
                    ForEach(ScanMode.allCases, id: \.self) { mode in Text(mode.label).tag(mode) }
                }
                .pickerStyle(.segmented).padding(.horizontal)

                Group {
                    if let image, imageSize != .zero {
                        GeometryReader { proxy in adjustmentCanvas(image: image, available: proxy.size) }
                            .background(Color.black).clipShape(RoundedRectangle(cornerRadius: 12))
                    } else if let error {
                        ContentUnavailableView("Couldn’t load the original", systemImage: "exclamationmark.triangle", description: Text(error))
                    } else {
                        ProgressView("Loading original…")
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity).padding(.horizontal)

                Text("Drag each numbered handle to a corner of the paper. B&W is an approximate preview; the server creates the final scan.")
                    .font(.footnote).foregroundStyle(.secondary).padding(.horizontal)
                if image != nil, let error { Text(error).font(.footnote).foregroundStyle(.red).padding(.horizontal) }
                if saving { ProgressView("Queuing adjusted scan…").tint(.scannyRed) }
            }
            .padding(.vertical)
            .navigationTitle("Adjust Scan").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save() }.bold().disabled(saving || points.count != 4) }
            }
            .task { await loadOriginal() }
            .interactiveDismissDisabled(saving)
        }
    }

    private func adjustmentCanvas(image: UIImage, available: CGSize) -> some View {
        let rect = fittedRect(image: imageSize, inside: available)
        return ZStack {
            Image(uiImage: image).resizable().aspectRatio(contentMode: .fit)
                .grayscale(mode == .blackAndWhite ? 1 : 0).contrast(mode == .blackAndWhite ? 1.35 : 1)
                .frame(width: rect.width, height: rect.height).position(x: rect.midX, y: rect.midY)
            let polygon = Path { path in
                let ordered = ScanCorner.allCases.compactMap { points[$0].map { screenPoint($0, in: rect) } }
                guard let first = ordered.first else { return }
                path.move(to: first)
                for point in ordered.dropFirst() { path.addLine(to: point) }
                path.closeSubpath()
            }
            polygon.fill(Color.scannyRed.opacity(0.13))
            polygon.stroke(Color.scannyRed, lineWidth: 3)

            ForEach(ScanCorner.allCases) { corner in
                if let point = points[corner] {
                    ZStack {
                        Circle().fill(.white).stroke(Color.scannyRed, lineWidth: 4).frame(width: 46, height: 46)
                            .shadow(color: .black.opacity(0.25), radius: 4, y: 2)
                        Text(corner.number).font(.headline).foregroundStyle(Color.scannyRed)
                    }
                    .position(screenPoint(point, in: rect))
                    .gesture(
                        DragGesture(minimumDistance: 0, coordinateSpace: .named("adjustCanvas"))
                            .onChanged { value in points[corner] = imagePoint(value.location, in: rect) }
                    )
                    .accessibilityLabel("Corner \(corner.number)")
                }
            }
        }
        .coordinateSpace(name: "adjustCanvas")
    }

    private func fittedRect(image: CGSize, inside available: CGSize) -> CGRect {
        let scale = min(available.width / image.width, available.height / image.height)
        let size = CGSize(width: image.width * scale, height: image.height * scale)
        return CGRect(x: (available.width - size.width) / 2, y: (available.height - size.height) / 2, width: size.width, height: size.height)
    }

    private func screenPoint(_ point: CGPoint, in rect: CGRect) -> CGPoint {
        CGPoint(x: rect.minX + point.x / imageSize.width * rect.width, y: rect.minY + point.y / imageSize.height * rect.height)
    }

    private func imagePoint(_ point: CGPoint, in rect: CGRect) -> CGPoint {
        CGPoint(
            x: max(0, min(imageSize.width, (point.x - rect.minX) / rect.width * imageSize.width)),
            y: max(0, min(imageSize.height, (point.y - rect.minY) / rect.height * imageSize.height))
        )
    }

    private func loadOriginal() async {
        do {
            let data = try await state.api.data(from: document.originalImageUrl)
            guard let image = UIImage(data: data) else { throw APIError.invalidResponse }
            self.image = image
            imageSize = CGSize(
                width: CGFloat(image.cgImage?.width ?? Int(image.size.width)),
                height: CGFloat(image.cgImage?.height ?? Int(image.size.height))
            )
            points = initialPoints(size: imageSize)
        } catch { self.error = error.localizedDescription }
    }

    private func initialPoints(size: CGSize) -> [ScanCorner: CGPoint] {
        func point(_ values: [Double]?) -> CGPoint? {
            guard let values, values.count == 2 else { return nil }
            return CGPoint(
                x: max(0, min(size.width, CGFloat(values[0]))),
                y: max(0, min(size.height, CGFloat(values[1])))
            )
        }
        if let corners = document.detectedCorners,
           let topLeft = point(corners.topLeft), let topRight = point(corners.topRight),
           let bottomRight = point(corners.bottomRight), let bottomLeft = point(corners.bottomLeft) {
            return [.topLeft: topLeft, .topRight: topRight, .bottomRight: bottomRight, .bottomLeft: bottomLeft]
        }
        let insetX = size.width * 0.06, insetY = size.height * 0.06
        return [
            .topLeft: CGPoint(x: insetX, y: insetY), .topRight: CGPoint(x: size.width - insetX, y: insetY),
            .bottomRight: CGPoint(x: size.width - insetX, y: size.height - insetY), .bottomLeft: CGPoint(x: insetX, y: size.height - insetY)
        ]
    }

    private func save() {
        guard let topLeft = points[.topLeft], let topRight = points[.topRight],
              let bottomRight = points[.bottomRight], let bottomLeft = points[.bottomLeft] else { return }
        saving = true; error = nil
        let corners = ScanCorners(
            topLeft: [Double(topLeft.x), Double(topLeft.y)], topRight: [Double(topRight.x), Double(topRight.y)],
            bottomRight: [Double(bottomRight.x), Double(bottomRight.y)], bottomLeft: [Double(bottomLeft.x), Double(bottomLeft.y)]
        )
        Task {
            do {
                let processing = try await state.documentService.adjust(document.id, corners: corners, mode: mode)
                state.replace(processing)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                dismiss()
                Task { await state.monitorDocument(document.id) }
            } catch { self.error = error.localizedDescription }
            saving = false
        }
    }
}
