import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class ApiService {
  // IMPORTANT: Configure the correct backend URL based on your setup:
  // 
  // For Android Emulator: http://10.0.2.2:8000
  // For Physical Device: http://YOUR_COMPUTER_IP:8000
  //   - Find your computer's IP: 
  //     Linux/Mac: run 'ip addr' or 'ifconfig' and look for your network interface
  //     Windows: run 'ipconfig' and look for IPv4 Address
  //   - Make sure your phone and computer are on the same WiFi network
  //   - Make sure the backend server is running: cd backend && ./run_server.sh
  //
  // Common IP ranges: 192.168.1.x, 192.168.0.x, 10.0.0.x
  // To find your IP: run 'ip addr' (Linux) or 'ipconfig' (Windows)
  static const String baseUrl = 'http://192.168.1.64:8000';
  
  // Helper method to test connection
  static Future<bool> testConnection() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }
  
  // Identify car by code with optional variant matching parameters
  static Future<IdentifyResponse> identifyCar(
    String code, {
    int? year,
    String? series,
    String? color,
    String? seriesNumber,
  }) async {
    try {
      // Build query parameters for variant matching
      final queryParams = <String, String>{};
      if (year != null) queryParams['year'] = year.toString();
      if (series != null && series.isNotEmpty) queryParams['series'] = series;
      if (color != null && color.isNotEmpty) queryParams['color'] = color;
      if (seriesNumber != null && seriesNumber.isNotEmpty) queryParams['series_number'] = seriesNumber;
      
      final uri = Uri.parse('$baseUrl/identify/$code').replace(queryParameters: queryParams);
      
      final response = await http.get(
        uri,
        headers: {'Content-Type': 'application/json'},
      ).timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          throw Exception('Connection timeout. Check if backend is running at $baseUrl');
        },
      );
      
      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body);
        return IdentifyResponse.fromJson(jsonData);
      } else if (response.statusCode == 404) {
        throw Exception('Car not found');
      } else {
        throw Exception('Failed to identify car: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Error identifying car: $e');
    }
  }
  
  // Add variant to collection
  static Future<CollectionItem> addToCollection(String variantId) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/collection'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'variant_id': variantId}),
      ).timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          throw Exception('Connection timeout. Check if backend is running at $baseUrl');
        },
      );
      
      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body);
        return CollectionItem.fromJson(jsonData);
      } else {
        throw Exception('Failed to add to collection: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Error adding to collection: $e');
    }
  }
  
  // Get user collection
  static Future<List<CollectionItem>> getCollection() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/collection'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          throw Exception(
            'Connection timeout.\n\n'
            'Troubleshooting:\n'
            '1. Make sure backend is running: cd backend && ./run_server.sh\n'
            '2. Check if IP address is correct: $baseUrl\n'
            '3. Ensure phone and computer are on the same WiFi network\n'
            '4. Try accessing $baseUrl in your phone\'s browser'
          );
        },
      );
      
      if (response.statusCode == 200) {
        final List<dynamic> jsonData = json.decode(response.body);
        return jsonData.map((item) => CollectionItem.fromJson(item)).toList();
      } else {
        throw Exception('Failed to get collection: ${response.statusCode}');
      }
    } on SocketException catch (e) {
      throw Exception(
        'Cannot connect to backend server.\n\n'
        'Error: ${e.message}\n\n'
        'Troubleshooting:\n'
        '1. Backend URL: $baseUrl\n'
        '2. Make sure backend is running: cd backend && ./run_server.sh\n'
        '3. Check if IP address is correct (find your computer\'s IP)\n'
        '4. Ensure phone and computer are on the same WiFi network\n'
        '5. For Android Emulator, use: http://10.0.2.2:8000\n'
        '6. Check firewall settings on your computer'
      );
    } catch (e) {
      if (e.toString().contains('SocketException') || 
          e.toString().contains('Failed host lookup') ||
          e.toString().contains('No route to host')) {
        throw Exception(
          'Cannot connect to backend server.\n\n'
          'Troubleshooting:\n'
          '1. Backend URL: $baseUrl\n'
          '2. Make sure backend is running: cd backend && ./run_server.sh\n'
          '3. Check if IP address is correct (find your computer\'s IP)\n'
          '4. Ensure phone and computer are on the same WiFi network\n'
          '5. For Android Emulator, use: http://10.0.2.2:8000\n'
          '6. Check firewall settings on your computer'
        );
      }
      throw Exception('Error getting collection: $e');
    }
  }
  
  // Get all toy numbers from database for OCR pattern matching
  static Future<List<String>> getAllToyNumbers() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/toy-numbers'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          throw Exception('Connection timeout. Check if backend is running at $baseUrl');
        },
      );
      
      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body);
        final List<dynamic> toyNumbers = jsonData['toy_numbers'] ?? [];
        return toyNumbers.cast<String>();
      } else {
        throw Exception('Failed to get toy numbers: ${response.statusCode}');
      }
    } catch (e) {
      throw Exception('Error getting toy numbers: $e');
    }
  }
  
  // Extract model code using Gemini API
  // Returns a map with toy_number and optional variant matching data
  static Future<Map<String, dynamic>?> extractModelCodeWithGemini(File imageFile) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/ocr/gemini'),
      );
      
      // Add image file to request
      final imageBytes = await imageFile.readAsBytes();
      request.files.add(
        http.MultipartFile.fromBytes(
          'file',
          imageBytes,
          filename: 'image.jpg',
        ),
      );
      
      // Send request with timeout
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 30),
        onTimeout: () {
          throw Exception('Connection timeout. Check if backend is running at $baseUrl');
        },
      );
      
      final response = await http.Response.fromStream(streamedResponse);
      
      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body);
        final toyNumber = jsonData['toy_number'] as String?; // Backend returns toy_number, not model_code
        final confidence = jsonData['confidence'] as double? ?? 0.0;
        
        // Only return data if confidence is reasonable and toy_number exists
        if (toyNumber != null && confidence > 0.5) {
          return {
            'toy_number': toyNumber,
            'release_year': jsonData['release_year'],
            'series_name': jsonData['series_name'],
            'body_color': jsonData['body_color'],
            'confidence': confidence,
          };
        }
        return null;
      } else {
        throw Exception('Failed to extract model code: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      throw Exception('Error extracting model code with Gemini: $e');
    }
  }
}
