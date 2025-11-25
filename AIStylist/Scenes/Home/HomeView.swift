//
//  HomeView.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 25.11.2025.
//

import SwiftUI

struct HomeView: View {
    @State private var selectedStyle: StyleModel = .casual

    var body: some View {
        ZStack {
            Color(.systemGray6)
                .ignoresSafeArea()

            //MARK: Weather Header View
            VStack(alignment: .leading) {
                WeatherHeaderView(
                    temperature: "32°",
                    condition: "Sunny",
                    systemImageName: "sun.max.fill"
                )
                .padding(.horizontal, 24)
                .padding(.top, 24)

             //MARK: Style Title
                VStack(alignment: .leading, spacing: 4) {
                    Text("Style Recommendations")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundColor(.primary)
                    Text("AI-picked looks for today's weather.")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 24)
                .padding(.top, 16)

            // MARK: Toggle
                StyleModeToggleView(selectedStyle: $selectedStyle)
                    .padding(.horizontal, 24)
                    .padding(.top, 16)
                Spacer()
            }
        }
    }
}

#Preview {
    HomeView()
}
