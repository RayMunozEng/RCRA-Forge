#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "StrandGroomAsset.generated.h"

USTRUCT(BlueprintType)
struct FURAUTHORING_API FStrandGroomBoneInfluence
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    FName Bone;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom", meta=(ClampMin="0", ClampMax="1"))
    float Weight = 0.f;
};

/** One authored strand guide. Control vertices are actor-local centimeters. */
USTRUCT(BlueprintType)
struct FURAUTHORING_API FStrandGroomGuide
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    TArray<FVector> ControlVertices;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    FVector RootNormal = FVector::UpVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    FVector RootFrameY = FVector::RightVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    FVector2D RootUV = FVector2D::ZeroVector;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom", meta=(ClampMin="0.0"))
    float WidthScale = 1.f;

    /** Exact retail triangle binding reduced through the source mesh's skin weights. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Strand Groom")
    TArray<FStrandGroomBoneInfluence> BoneInfluences;
};

/** Authored guide data for discrete ear, face, tail, or crest strands. */
UCLASS(BlueprintType)
class FURAUTHORING_API UStrandGroomAsset : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Strand Groom")
    TArray<FStrandGroomGuide> Guides;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Strand Groom", meta=(ClampMin="4", ClampMax="20"))
    int32 Tessellation = 8;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Strand Groom", meta=(ClampMin="1", ClampMax="64"))
    int32 StrandsPerClump = 1;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Strand Groom", meta=(ClampMin="0"))
    float CapturedMaxWindOffsetCm = 0.f;
};
