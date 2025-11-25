//
//  SplashView.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 5.11.2025
//

import SwiftUI

struct SplashView: View {
    @State private var iconScale: CGFloat = 0.7
    @State private var iconOpacity: Double = 0
    @State private var pillOpacity: Double = 0
    @State private var titleOpacity: Double = 0
    @State private var subtitleOpacity: Double = 0
    @State private var buttonsOpacity: Double = 0

    @State private var currentPage: Int = 0
    @State private var pageTimer: Timer?

    private let pages: [OnboardingPage] = [
        OnboardingPage(
            systemImageName: "tshirt.fill",
            pillText: "AI Outfit Detection",
            titleLine1: "Effortless style",
            titleLine2Prefix: "with",
            titleLine2Highlight: "AIStylist",
            subtitle: "Capture any piece from your wardrobe and let AIStylist create personalized outfit ideas around it."
        ),
        OnboardingPage(
            systemImageName: "camera.viewfinder",
            pillText: "Smart Capture",
            titleLine1: "Snap your look",
            titleLine2Prefix: "and get",
            titleLine2Highlight: "instant ideas",
            subtitle: "Use your camera to capture outfits or single items and get AI-powered suggestions in just a few seconds."
        ),
        OnboardingPage(
            systemImageName: "square.grid.2x2.fill",
            pillText: "Digital Wardrobe",
            titleLine1: "Organize your",
            titleLine2Prefix: "entire",
            titleLine2Highlight: "closet",
            subtitle: "Save your favorite pieces, tag them by season, color and occasion, and build a wardrobe you can carry in your pocket."
        ),
        OnboardingPage(
            systemImageName: "sparkles",
            pillText: "Personal Styling",
            titleLine1: "Style that",
            titleLine2Prefix: "adapts to",
            titleLine2Highlight: "you",
            subtitle: "AIStylist learns from the looks you save and love, so every new recommendation feels more like your personal stylist."
        )
    ]

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color.black,
                    Color(.sRGB, white: 0.05, opacity: 1.0),
                    Color.black
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer(minLength: 40)
                TabView(selection: $currentPage) {
                    ForEach(pages.indices, id: \.self) { index in
                        singlePage(pages[index])
                            .tag(index)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))

                Spacer()

                HStack(spacing: 8) {
                    ForEach(pages.indices, id: \.self) { index in
                        Circle()
                            .fill(index == currentPage ? Color.white : Color.white.opacity(0.35))
                            .frame(width: 6, height: 6)
                    }
                }
                .padding(.top, -60)
                .opacity(subtitleOpacity)

                VStack(spacing: 14) {
                    Button {
                        let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene
                           windowScene?.windows.first?.rootViewController = UIHostingController(rootView: HomeView())
                    } label: {
                        Text("Get Started")
                            .font(.system(size: 17, weight: .semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(
                                RoundedRectangle(cornerRadius: 26, style: .continuous)
                                    .fill(
                                        LinearGradient(
                                            colors: [
                                                Color(.sRGB, red: 0.98, green: 0.47, blue: 0.60, opacity: 1.0),
                                                Color(.sRGB, red: 0.70, green: 0.40, blue: 0.95, opacity: 1.0)
                                            ],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        )
                                    )
                                    .shadow(color: Color.black.opacity(0.7), radius: 18, x: 0, y: 12)
                            )
                            .foregroundColor(.white)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 36)
                .opacity(buttonsOpacity)
            }
        }
        .onAppear {
            startAnimation()
            startAutoPageChange()
        }
        .onDisappear {
            pageTimer?.invalidate()
        }
    }

    private func singlePage(_ page: OnboardingPage) -> some View {
        VStack(spacing: 0) {
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                Color.purple.opacity(0.5),
                                Color.clear
                            ],
                            center: .center,
                            startRadius: 0,
                            endRadius: 220
                        )
                    )
                    .frame(width: 260, height: 260)
                    .opacity(iconOpacity)

                Circle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(.sRGB, red: 0.98, green: 0.47, blue: 0.60, opacity: 1.0),
                                Color(.sRGB, red: 0.70, green: 0.40, blue: 0.95, opacity: 1.0)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .overlay(
                        Circle()
                            .stroke(Color.white.opacity(0.3), lineWidth: 1.4)
                    )
                    .shadow(color: Color.purple.opacity(0.6), radius: 26, x: 0, y: 18)
                    .frame(width: 160, height: 160)

                Image(systemName: page.systemImageName)
                    .font(.system(size: 56, weight: .semibold))
                    .foregroundColor(.white)
            }
            .scaleEffect(iconScale)
            .opacity(iconOpacity)
            .padding(.top, -90)

            Text(page.pillText)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white)
                .padding(.horizontal, 18)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                        .overlay(
                            Capsule()
                                .stroke(Color.white.opacity(0.25), lineWidth: 1)
                        )
                )
                .padding(.top, 24)
                .opacity(pillOpacity)

            VStack(alignment: .leading, spacing: 4) {
                Text(page.titleLine1)
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundColor(.white)

                HStack(spacing: 4) {
                    Text(page.titleLine2Prefix)
                        .font(.system(size: 34, weight: .semibold))
                        .foregroundColor(.white.opacity(0.85))

                    Text(page.titleLine2Highlight)
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [
                                    Color(.sRGB, red: 0.98, green: 0.47, blue: 0.60, opacity: 1.0),
                                    Color(.sRGB, red: 0.70, green: 0.40, blue: 0.95, opacity: 1.0)
                                ],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 32)
            .padding(.top, 54)
            .opacity(titleOpacity)

            Text(page.subtitle)
                .font(.system(size: 15))
                .foregroundColor(.white.opacity(0.7))
                .lineSpacing(4)
                .padding(.top, 16)
                .padding(.horizontal, 32)
                .multilineTextAlignment(.leading)
                .opacity(subtitleOpacity)
        }
    }

    private func startAnimation() {
        withAnimation(.spring(response: 0.9, dampingFraction: 0.75)) {
            iconOpacity = 1
            iconScale = 1.0
        }

        withAnimation(.easeOut(duration: 0.5).delay(0.25)) {
            pillOpacity = 1
        }

        withAnimation(.easeOut(duration: 0.6).delay(0.3)) {
            titleOpacity = 1
        }

        withAnimation(.easeOut(duration: 0.6).delay(0.45)) {
            subtitleOpacity = 1
        }

        withAnimation(.spring(response: 0.9, dampingFraction: 0.8).delay(0.7)) {
            buttonsOpacity = 1
        }
    }

    private func startAutoPageChange() {
        pageTimer?.invalidate()
        pageTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { _ in
            withAnimation(.easeInOut(duration: 0.4)) {
                currentPage = (currentPage + 1) % pages.count
            }
        }
    }
}

#Preview {
    SplashView()
}
