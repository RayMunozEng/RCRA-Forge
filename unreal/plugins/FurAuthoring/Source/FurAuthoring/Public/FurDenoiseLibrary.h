#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "FurDenoiseLibrary.generated.h"

/** Runtime controls for the recovered pre-TAA fur surface filter. */
UCLASS()
class FURAUTHORING_API UFurDenoiseLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Enable or disable filtering for visible materials tagged RecoveredFurSurface. */
    UFUNCTION(BlueprintCallable, Category="Fur|Filter")
    static bool SetRecoveredFurDenoiseEnabled(bool bEnabled);

    UFUNCTION(BlueprintPure, Category="Fur|Filter")
    static bool IsRecoveredFurDenoiseEnabled();

    /** True after the engine has registered the production scene-view extension. */
    UFUNCTION(BlueprintPure, Category="Fur|Filter")
    static bool IsRecoveredFurDenoiseRegistered();
};
