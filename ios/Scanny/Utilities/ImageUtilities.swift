import UIKit

enum ImageUtilities {
    static let maxLongEdge: CGFloat = 3000
    static let jpegQuality: CGFloat = 0.86

    static func uploadJPEG(from data: Data) -> Data? {
        autoreleasepool {
            guard let source = UIImage(data: data) else { return nil }
            let original = source.size
            let scale = min(1, maxLongEdge / max(original.width, original.height))
            let target = CGSize(width: original.width * scale, height: original.height * scale)
            let format = UIGraphicsImageRendererFormat()
            format.scale = 1; format.opaque = true
            let normalized = UIGraphicsImageRenderer(size: target, format: format).image { _ in
                UIColor.white.setFill(); UIRectFill(CGRect(origin: .zero, size: target))
                source.draw(in: CGRect(origin: .zero, size: target))
            }
            return normalized.jpegData(compressionQuality: jpegQuality)
        }
    }
}
