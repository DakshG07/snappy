import SwiftUI

struct AuthView: View {
    @Environment(AppState.self) private var state
    @State private var registering = false
    @State private var email = ""
    @State private var password = ""
    @State private var confirmation = ""
    @State private var busy = false
    @State private var error: String?
    @State private var showingServer = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    Spacer(minLength: 54)
                    VStack(spacing: 10) {
                        Image(systemName: "doc.viewfinder")
                            .font(.system(size: 54, weight: .semibold))
                            .foregroundStyle(Color.scannyRed)
                        Text("Scanny").font(.largeTitle.bold())
                        Text(registering ? "Create your account" : "Welcome back")
                            .foregroundStyle(.secondary)
                    }
                    VStack(spacing: 14) {
                        TextField("Email", text: $email)
                            .textInputAutocapitalization(.never).keyboardType(.emailAddress).textContentType(.emailAddress)
                        SecureField("Password", text: $password).textContentType(registering ? .newPassword : .password)
                        if registering { SecureField("Confirm password", text: $confirmation).textContentType(.newPassword) }
                    }
                    .textFieldStyle(.roundedBorder)
                    if let error { Text(error).font(.footnote).foregroundStyle(.red).frame(maxWidth: .infinity, alignment: .leading) }
                    Button(action: submit) {
                        Group { if busy { ProgressView().tint(.white) } else { Text(registering ? "Create Account" : "Sign In").bold() } }
                            .frame(maxWidth: .infinity).frame(height: 28)
                    }
                    .buttonStyle(.borderedProminent).tint(.scannyRed).controlSize(.large)
                    .disabled(busy || email.isEmpty || password.isEmpty || (registering && confirmation.isEmpty))
                    Button(registering ? "Already have an account? Sign In" : "New to Scanny? Register") {
                        withAnimation { registering.toggle(); error = nil }
                    }
                    .font(.subheadline).foregroundStyle(Color.scannyRed)
                    Spacer(minLength: 20)
                }
                .padding(.horizontal, 28)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Server", systemImage: "network") { showingServer = true }.labelStyle(.iconOnly)
                }
            }
            .sheet(isPresented: $showingServer) { ServerSettingsView() }
        }
    }

    private func submit() {
        guard !registering || password == confirmation else { error = "Passwords do not match."; return }
        guard !registering || password.count >= 8 else { error = "Password must be at least 8 characters."; return }
        busy = true; error = nil
        Task {
            do {
                if registering { try await state.register(email: email, password: password) }
                else { try await state.login(email: email, password: password) }
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}

struct ServerSettingsView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    @State private var address = ""
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Scanny server") {
                    TextField("http://mac-name.local:8000", text: $address)
                        .textInputAutocapitalization(.never).keyboardType(.URL)
                    Text("Use your Mac’s .local hostname or LAN address while developing on a physical iPhone.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
            }
            .navigationTitle("Server").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        do { try state.api.updateBaseURL(address); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }
                }
            }
            .onAppear { address = state.api.baseURL.absoluteString }
        }
        .presentationDetents([.medium])
    }
}
