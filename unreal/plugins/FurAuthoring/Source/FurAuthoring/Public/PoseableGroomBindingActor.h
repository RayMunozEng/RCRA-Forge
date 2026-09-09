#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "PoseableGroomBindingActor.generated.h"

class UPoseableMeshComponent;

/** Pose source used to validate strand binding against controlled bone motion. */
UCLASS(Blueprintable, meta=(DisplayName="Poseable Groom Binding Actor"))
class FURAUTHORING_API APoseableGroomBindingActor : public AActor
{
    GENERATED_BODY()
public:
    APoseableGroomBindingActor();

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Binding Test")
    TObjectPtr<UPoseableMeshComponent> PoseMesh;
};
