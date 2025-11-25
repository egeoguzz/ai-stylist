//
//  WeatherHeaderView.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 25.11.2025.
//

import SwiftUI

struct WeatherHeaderView: View {
    let temperature: String
    let condition: String
    let systemImageName: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImageName)
                .font(.system(size: 26))
                .foregroundColor(.yellow)

            VStack(alignment: .leading, spacing: 2) {
                Text(temperature)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(.primary)

                Text(condition)
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
    }
}
