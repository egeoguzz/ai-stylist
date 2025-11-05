//
//  OnboardingPage.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 5.11.2025.
//

import Foundation

struct OnboardingPage: Identifiable {
    let id = UUID()
    let systemImageName: String
    let pillText: String
    let titleLine1: String
    let titleLine2Prefix: String
    let titleLine2Highlight: String
    let subtitle: String
}
