//
//  StyleModel.swift
//  AIStylist
//
//  Created by Ezgi Özkan on 25.11.2025.
//

import Foundation

enum StyleModel: CaseIterable {
    case casual
    case formal

    var title: String {
        switch self {
        case .casual: return "Casual"
        case .formal: return "Formal"
        }
    }
}
