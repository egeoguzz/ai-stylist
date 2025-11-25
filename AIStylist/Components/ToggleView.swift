//
//  ToggleView.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 25.11.2025.
//

import SwiftUI

struct StyleModeToggleView: View {
    @Binding var selectedStyle: StyleModel
    private let basePurple = Color.purple

    var body: some View {
        ZStack {
            Capsule()
                .fill(basePurple.opacity(0.12))

            HStack(spacing: 0) {
                ForEach(StyleModel.allCases, id: \.self) { mode in
                    Button {
                        selectedStyle = mode
                    } label: {
                        ZStack {
                            if selectedStyle == mode {
                                Capsule()
                                    .fill(basePurple.opacity(0.75))
                            }

                            Text(mode.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(
                                    selectedStyle == mode
                                    ? .white
                                    : .primary
                                )
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(4)
        }
        .frame(height: 36)
    }
}
