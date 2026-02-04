class Car {
  final String id;
  final String? toyNumber; // Optional - get from first variant if needed
  final String name;
  final String brand;
  final List<Variant> variants;

  Car({
    required this.id,
    this.toyNumber,
    required this.name,
    required this.brand,
    required this.variants,
  });

  factory Car.fromJson(Map<String, dynamic> json) {
    final variants = (json['variants'] as List<dynamic>?)
        ?.map((v) => Variant.fromJson(v))
        .toList() ?? [];
    
    // Get toy_number from first variant if available (Car doesn't have toy_number directly)
    final toyNumber = json['toy_number'] as String? ?? 
                      (variants.isNotEmpty ? variants.first.toyNumber : null);
    
    return Car(
      id: json['id'],
      toyNumber: toyNumber,
      name: json['model_name'] ?? json['name'] ?? '', // Backend uses model_name
      brand: json['brand'],
      variants: variants,
    );
  }
}

class Variant {
  final String id;
  final String carId;
  final String toyNumber; // Backend Variant has toy_number
  final String desc;
  final bool isChase;
  final bool treasureHunt;
  final bool superTreasureHunt;
  final int? releaseYear;

  Variant({
    required this.id,
    required this.carId,
    required this.toyNumber,
    required this.desc,
    required this.isChase,
    required this.treasureHunt,
    required this.superTreasureHunt,
    this.releaseYear,
  });

  factory Variant.fromJson(Map<String, dynamic> json) {
    return Variant(
      id: json['id'],
      carId: json['car_id'],
      toyNumber: json['toy_number'] ?? '',
      desc: json['desc'],
      isChase: json['is_chase'] ?? false,
      treasureHunt: json['treasure_hunt'] ?? false,
      superTreasureHunt: json['super_treasure_hunt'] ?? false,
      releaseYear: json['release_year'] != null ? (json['release_year'] is int ? json['release_year'] : int.tryParse(json['release_year'].toString())) : null,
    );
  }
}

class IdentifyResponse {
  final Car car;

  IdentifyResponse({
    required this.car,
  });

  factory IdentifyResponse.fromJson(Map<String, dynamic> json) {
    return IdentifyResponse(
      car: Car.fromJson(json['car']),
    );
  }
}

class CollectionItem {
  final String id;
  final String variantId;
  final DateTime addedAt;
  final Variant variant;
  final Car? car;

  CollectionItem({
    required this.id,
    required this.variantId,
    required this.addedAt,
    required this.variant,
    this.car,
  });

  factory CollectionItem.fromJson(Map<String, dynamic> json) {
    return CollectionItem(
      id: json['id'],
      variantId: json['variant_id'],
      addedAt: DateTime.parse(json['added_at']),
      variant: Variant.fromJson(json['variant']),
      car: json['car'] != null ? Car.fromJson(json['car']) : null,
    );
  }
}
